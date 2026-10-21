from datetime import UTC, datetime

import numpy as np
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from radar.common.clickhouse import ClickHouseError
from radar.common.enums import Polarity
from radar.common.schemas import CdcPost, Prediction
from radar.common.settings import InferenceRole
from radar.ml.inference.main import (
    HashCache,
    Predictor,
    load_cache,
    predict,
    require_primary,
    select_posts,
    should_predict,
    text_hash,
)
from radar.ml.training.dataset import post_text
from radar.ml.training.train import ModelCard

NOW = datetime(2026, 10, 16, 3, 0, tzinfo=UTC)
PID = "Stock.M.1792000000.A.ABC"
MAX_CHARS = 20


def event(op: str = "c", post_id: str = PID, title: str = "t", content: str = "c", **kw) -> CdcPost:
    return CdcPost(post_id=post_id, board="Stock", title=title, content=content, op=op, **kw)


def card(max_chars: int = MAX_CHARS) -> ModelCard:
    return ModelCard(
        model_version="tfidf-lr-20261016T0300",
        created_at=NOW,
        dataset="d.jsonl",
        labeler="groq:q",
        label_version="prompt-v6",
        max_chars=max_chars,
        n_train=6,
        class_counts={"positive": 2, "negative": 2, "neutral": 2},
        params={"seed": 42},
    )


class FakePipeline:
    """predict_proba 回傳固定分數；記錄呼叫次數與輸入。"""

    def __init__(self, classes=("negative", "neutral", "positive"), row=(0.7, 0.2, 0.1)):
        self.classes_ = np.array(classes)
        self._row = row
        self.calls: list[list[str]] = []

    def predict_proba(self, texts):
        self.calls.append(list(texts))
        return np.array([self._row for _ in texts])


class Sink:
    def __init__(self, fail_flush: bool = False) -> None:
        self.published: list[Prediction] = []
        self.flushed = 0
        self.fail_flush = fail_flush

    def publish(self, p: Prediction) -> None:
        self.published.append(p)

    def flush(self) -> None:
        if self.fail_flush:
            raise TimeoutError("not delivered")
        self.flushed += 1


def predictor(pipeline=None, sink=None, cache=None) -> tuple[Predictor, Sink, HashCache]:
    sink = sink or Sink()
    cache = cache or HashCache(100)
    handler = Predictor(
        pipeline or FakePipeline(), card(), cache, sink.publish, sink.flush, lambda: NOW
    )
    return handler, sink, cache


class FakeClickHouse:
    """query_rows 回傳固定的列並記錄參數；raise_error 時模擬 ClickHouse 連不上。"""

    def __init__(self, rows=(), raise_error: Exception | None = None) -> None:
        self.rows = list(rows)
        self.raise_error = raise_error
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def query_rows(self, sql, params=None):
        self.calls.append((sql, params))
        if self.raise_error:
            raise self.raise_error
        return self.rows


# --- text_hash / HashCache ---


def test_text_hash_same_text_same_digest():
    assert text_hash("標題\n內文") == text_hash("標題\n內文")


def test_text_hash_different_text_different_digest():
    assert text_hash("a") != text_hash("b")


def test_hash_cache_miss_returns_none():
    assert HashCache(10).get(PID) is None


def test_hash_cache_evicts_least_recently_used_over_max_size():
    cache = HashCache(2)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.put("c", "3")

    assert cache.get("a") is None
    assert len(cache) == 2


def test_hash_cache_get_refreshes_recency():
    cache = HashCache(2)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.get("a")
    cache.put("c", "3")

    assert cache.get("a") == "1"
    assert cache.get("b") is None


# --- should_predict ---


def test_should_predict_new_post_not_in_cache_predicts():
    assert should_predict("c", None, "h")


def test_should_predict_update_not_in_cache_does_not_predict():
    assert not should_predict("u", None, "h")


def test_should_predict_snapshot_not_in_cache_does_not_predict():
    assert not should_predict("r", None, "h")


@pytest.mark.parametrize("op", ["c", "u", "r"])
def test_should_predict_same_hash_does_not_predict_for_any_op(op):
    assert not should_predict(op, "h", "h")


def test_should_predict_changed_hash_predicts_for_update():
    assert should_predict("u", "old", "new")


# --- select_posts ---


def test_select_posts_push_count_only_update_is_skipped():
    cache = HashCache(10)
    cache.put(PID, text_hash(post_text("t", "c", MAX_CHARS)))

    selection = select_posts([event(op="u")], cache, MAX_CHARS)

    assert selection.to_predict == []
    assert PID in selection.seen


def test_select_posts_content_edit_beyond_max_chars_is_skipped():
    head = "x" * MAX_CHARS
    cache = HashCache(10)
    cache.put(PID, text_hash(post_text("t", head + "old tail", MAX_CHARS)))

    selection = select_posts([event(op="u", content=head + "new tail")], cache, MAX_CHARS)

    assert selection.to_predict == []


def test_select_posts_content_edit_within_max_chars_predicts():
    cache = HashCache(10)
    cache.put(PID, text_hash(post_text("t", "old", MAX_CHARS)))

    selection = select_posts([event(op="u", content="new")], cache, MAX_CHARS)

    assert [p.post_id for p in selection.to_predict] == [PID]


def test_select_posts_deleted_post_is_skipped_and_not_remembered():
    selection = select_posts([event(is_deleted=True)], HashCache(10), MAX_CHARS)

    assert selection.to_predict == []
    assert selection.seen == {}


def test_select_posts_pg_row_deleted_event_is_skipped():
    selection = select_posts([event(op="d", __deleted="true")], HashCache(10), MAX_CHARS)

    assert selection.to_predict == []
    assert selection.seen == {}


def test_select_posts_same_post_twice_in_batch_uses_last_event():
    events = [event(op="c", content="first"), event(op="u", content="second")]

    selection = select_posts(events, HashCache(10), MAX_CHARS)

    # 新文章後面接著推噓數更新：只推論一次，用最後一筆的文字
    assert len(selection.to_predict) == 1
    assert selection.to_predict[0].text == post_text("t", "second", MAX_CHARS)


def test_select_posts_seen_includes_posts_not_predicted():
    other = "Stock.M.1792000001.A.DEF"
    events = [event(op="c"), event(op="u", post_id=other)]

    selection = select_posts(events, HashCache(10), MAX_CHARS)

    assert [p.post_id for p in selection.to_predict] == [PID]
    assert set(selection.seen) == {PID, other}


def test_select_posts_text_matches_training_post_text():
    selection = select_posts([event(title=" 標題 ", content="內文" * 20)], HashCache(10), MAX_CHARS)

    assert selection.to_predict[0].text == post_text(" 標題 ", "內文" * 20, MAX_CHARS)


# --- predict ---


def test_predict_maps_classes_to_polarity_scores():
    pipeline = FakePipeline(classes=("positive", "negative", "neutral"), row=(0.1, 0.6, 0.3))

    [(polarity, scores)] = predict(pipeline, ["x"])

    assert scores == {Polarity.POSITIVE: 0.1, Polarity.NEGATIVE: 0.6, Polarity.NEUTRAL: 0.3}
    assert polarity is Polarity.NEGATIVE


def test_predict_polarity_is_highest_score_with_real_model():
    texts = ["好棒 讚", "超讚 推", "爛 垃圾", "糟糕 爛", "今天 下雨", "明天 開會"]
    labels = ["positive", "positive", "negative", "negative", "neutral", "neutral"]
    pipeline = Pipeline(
        [("tfidf", TfidfVectorizer(analyzer="char", ngram_range=(1, 2))),
         ("lr", LogisticRegression())]
    ).fit(texts, labels)  # fmt: skip

    results = predict(pipeline, ["好棒 讚", "爛 垃圾"])

    for polarity, scores in results:
        assert set(scores) == set(Polarity)
        assert scores[polarity] == max(scores.values())
        assert abs(sum(scores.values()) - 1) < 1e-9


def test_predict_missing_class_scores_zero():
    pipeline = FakePipeline(classes=("negative", "neutral"), row=(0.8, 0.2))

    [(_, scores)] = predict(pipeline, ["x"])

    assert scores[Polarity.POSITIVE] == 0.0


def test_predict_empty_texts_returns_empty_without_calling_model():
    pipeline = FakePipeline()

    assert predict(pipeline, []) == []
    assert pipeline.calls == []


# --- Predictor ---


def test_predictor_publishes_prediction_with_model_version_and_flushes():
    handler, sink, _ = predictor()

    handler([event(op="c")])

    [p] = sink.published
    assert (p.post_id, p.model_version, p.predicted_at) == (PID, "tfidf-lr-20261016T0300", NOW)
    assert p.polarity is Polarity.NEGATIVE
    assert sink.flushed == 1


def test_predictor_duplicate_event_publishes_once():
    handler, sink, _ = predictor()

    handler([event(op="c")])
    handler([event(op="c")])  # Connect 重啟重送

    assert len(sink.published) == 1


def test_predictor_push_count_updates_after_create_publish_once():
    handler, sink, _ = predictor()

    handler([event(op="c")])
    handler([event(op="u"), event(op="u")])

    assert len(sink.published) == 1


def test_predictor_updates_cache_only_after_flush_succeeds():
    handler, _, cache = predictor(sink=Sink(fail_flush=True))

    with pytest.raises(TimeoutError):
        handler([event(op="c")])

    assert cache.get(PID) is None  # 整批重試時仍會推論


def test_predictor_batch_without_posts_to_predict_does_not_call_model():
    pipeline = FakePipeline()
    handler, sink, cache = predictor(pipeline=pipeline)

    handler([event(op="u")])

    assert pipeline.calls == []
    assert sink.flushed == 0
    assert cache.get(PID) is not None  # 記下 hash，之後的內文編輯才偵測得到


def test_predictor_model_error_propagates():
    class Broken(FakePipeline):
        def predict_proba(self, texts):
            raise ValueError("bad model")

    handler, _, _ = predictor(pipeline=Broken())

    with pytest.raises(ValueError):
        handler([event(op="c")])


# --- load_cache（#37）---

H1, H2, H3 = "1" * 64, "2" * 64, "3" * 64


def test_load_cache_puts_each_post_hash_and_returns_count():
    ch = FakeClickHouse([{"post_id": "a", "latest_hash": H1}, {"post_id": "b", "latest_hash": H2}])
    cache = HashCache(100)

    loaded = load_cache(ch, "tfidf-lr-1", cache)

    assert loaded == 2
    assert (cache.get("a"), cache.get("b")) == (H1, H2)


def test_load_cache_queries_only_current_model_version():
    ch = FakeClickHouse()

    load_cache(ch, "tfidf-lr-1", HashCache(10))

    [(sql, params)] = ch.calls
    assert params == {"model_version": "tfidf-lr-1"}
    assert "model_version = {model_version:String}" in sql
    assert "text_hash != ''" in sql


def test_load_cache_no_rows_leaves_cache_empty():
    cache = HashCache(10)

    assert load_cache(FakeClickHouse(), "tfidf-lr-1", cache) == 0
    assert len(cache) == 0


def test_load_cache_rows_oldest_first_keep_newest_when_over_max_size():
    rows = [{"post_id": p, "latest_hash": h} for p, h in [("old", H1), ("mid", H2), ("new", H3)]]
    cache = HashCache(2)

    load_cache(FakeClickHouse(rows), "tfidf-lr-1", cache)

    assert cache.get("old") is None
    assert (cache.get("mid"), cache.get("new")) == (H2, H3)


def test_load_cache_clickhouse_error_propagates():
    ch = FakeClickHouse(raise_error=ClickHouseError("503: unavailable"))

    with pytest.raises(ClickHouseError):
        load_cache(ch, "tfidf-lr-1", HashCache(10))


def loaded_predictor(title: str, content: str) -> tuple[Predictor, Sink]:
    """模擬重啟：快取由 ClickHouse 載入這篇上次推論的 hash。"""
    cache = HashCache(100)
    digest = text_hash(post_text(title, content, MAX_CHARS))
    load_cache(FakeClickHouse([{"post_id": PID, "latest_hash": digest}]), "v", cache)
    handler, sink, _ = predictor(cache=cache)
    return handler, sink


def test_restarted_predictor_with_loaded_cache_predicts_edited_existing_post():
    handler, sink = loaded_predictor("t", "舊內文")

    handler([event(op="u", content="編輯後的內文")])

    assert [p.post_id for p in sink.published] == [PID]


def test_restarted_predictor_with_loaded_cache_skips_push_count_only_update():
    handler, sink = loaded_predictor("t", "內文")

    handler([event(op="u", content="內文")])  # 只有推噓數變動，文字相同

    assert sink.published == []


def test_restarted_predictor_without_loaded_cache_misses_edit():
    """修正前的行為：快取是空的時 op=u 不推論（#37 的現象，載入快取才解決）。"""
    handler, sink, _ = predictor()

    handler([event(op="u", content="編輯後的內文")])

    assert sink.published == []


def test_predictor_publishes_text_hash_of_model_input():
    handler, sink, _ = predictor()

    handler([event(op="c", title="標題", content="內文")])

    [p] = sink.published
    assert p.text_hash == text_hash(post_text("標題", "內文", MAX_CHARS))


def test_require_primary_accepts_primary():
    require_primary(InferenceRole.PRIMARY)


def test_require_primary_rejects_shadow_until_implemented():
    with pytest.raises(NotImplementedError):
        require_primary(InferenceRole.SHADOW)

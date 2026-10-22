"""驗收 bert-classifier（開發規格 7.27「載入」「模型包格式」）：只走對外行為。

模型用 tests/helpers/onnx_model.py 的小模型；關鍵字決定類別（好棒→正面、爛糟→負面）。
"""

import json
import subprocess
import sys
from pathlib import Path

import onnxruntime
import pytest

# NOTE: 目錄名含連字號，不能放 __init__.py；補上 rootdir 才能 import tests.*
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.helpers.onnx_model import build_model_dir
from tests.unit.ml.fakes import FakeClassifier

from radar.common.enums import Polarity
from radar.ml.training import classifier as classifier_module
from radar.ml.training import evaluate
from radar.ml.training.classifier import (
    Classifier,
    SklearnClassifier,
    load_classifier,
    top_class,
)
from radar.ml.training.train import ModelCard, ModelKind, build_pipeline, save_model

POS_TEXT = "今天好棒"
NEG_TEXT = "爛糟慘"
NEU_TEXT = "今天的公告"
REPO_ROOT = Path(__file__).resolve().parents[4]


def assert_valid_scores(scores: dict[Polarity, float]) -> None:
    assert set(scores) == set(Polarity)
    assert all(0.0 <= v <= 1.0 for v in scores.values())
    assert sum(scores.values()) == pytest.approx(1.0, abs=1e-5)


# ---- top_class ----


def test_top_class_returns_highest_score():
    scores = {Polarity.POSITIVE: 0.2, Polarity.NEGATIVE: 0.5, Polarity.NEUTRAL: 0.3}
    assert top_class(scores) is Polarity.NEGATIVE


def test_top_class_tie_takes_first_in_polarity_declaration_order():
    tied = dict.fromkeys(reversed(list(Polarity)), 1 / 3)
    assert top_class(tied) is list(Polarity)[0]


# ---- sklearn ----


def _two_class_pipeline():
    pipeline = build_pipeline(seed=0)
    pipeline.set_params(tfidf__min_df=1)
    texts = ["好棒讚", "很好棒", "爛糟慘", "好爛糟", "讚讚好", "慘爛爛"]
    labels = [
        Polarity.POSITIVE.value,
        Polarity.POSITIVE.value,
        Polarity.NEGATIVE.value,
        Polarity.NEGATIVE.value,
        Polarity.POSITIVE.value,
        Polarity.NEGATIVE.value,
    ]
    return pipeline.fit(texts, labels)


def test_sklearn_missing_class_is_filled_with_zero_and_sums_to_one():
    clf: Classifier = SklearnClassifier(_two_class_pipeline())
    results = clf.predict_proba(["好棒", "爛糟", "不認識的字"])
    assert len(results) == 3
    for scores in results:
        assert_valid_scores(scores)
        assert scores[Polarity.NEUTRAL] == 0.0


def test_sklearn_empty_input_returns_empty_list():
    assert SklearnClassifier(_two_class_pipeline()).predict_proba([]) == []


def test_sklearn_scores_follow_the_text():
    scores = SklearnClassifier(_two_class_pipeline()).predict_proba(["好棒讚", "爛糟慘"])
    assert top_class(scores[0]) is Polarity.POSITIVE
    assert top_class(scores[1]) is Polarity.NEGATIVE


def _legacy_card(version: str) -> ModelCard:
    return ModelCard(
        model_version=version,
        created_at="2026-10-01T00:00:00Z",
        dataset="d",
        labeler="groq",
        label_version="v",
        max_chars=2000,
        n_train=6,
        class_counts={},
        params={},
    )


def test_load_classifier_loads_legacy_baseline_card_without_new_fields(tmp_path: Path):
    model_dir = save_model(_two_class_pipeline(), _legacy_card("tfidf-lr-202610010000"), tmp_path)
    card_path = model_dir / "model_card.json"
    raw = json.loads(card_path.read_text())
    for key in ("kind", "base_model", "max_len", "labels", "files"):
        raw.pop(key, None)
    card_path.write_text(json.dumps(raw))

    clf, card = load_classifier(model_dir, threads=1)

    assert card.kind is ModelKind.SKLEARN
    assert card.model_version == "tfidf-lr-202610010000"
    [scores] = clf.predict_proba(["好棒讚"])
    assert_valid_scores(scores)


# ---- ONNX ----


@pytest.mark.parametrize("fixture", ["tiny_model_dir", "tiny_int8_model_dir"])
def test_load_classifier_runs_fp32_and_int8_onnx_models(fixture: str, request):
    model_dir: Path = request.getfixturevalue(fixture)

    clf, card = load_classifier(model_dir, threads=1)

    assert card.kind is ModelKind.ONNX
    assert card.model_version == model_dir.name
    results = clf.predict_proba([POS_TEXT, NEG_TEXT, NEU_TEXT])
    assert len(results) == 3
    for scores in results:
        assert_valid_scores(scores)
    assert [top_class(s) for s in results] == [
        Polarity.POSITIVE,
        Polarity.NEGATIVE,
        Polarity.NEUTRAL,
    ]


def test_onnx_empty_input_returns_empty_list(tiny_model_dir: Path):
    clf, _ = load_classifier(tiny_model_dir, threads=1)
    assert clf.predict_proba([]) == []


def test_onnx_batch_padding_does_not_change_each_result(tiny_model_dir: Path):
    clf, _ = load_classifier(tiny_model_dir, threads=1)
    texts = ["好", POS_TEXT + "好棒讚漲" * 3, NEG_TEXT, ""]
    together = clf.predict_proba(texts)
    alone = [clf.predict_proba([t])[0] for t in texts]
    for a, b in zip(together, alone, strict=True):
        for polarity in Polarity:
            assert a[polarity] == pytest.approx(b[polarity], abs=1e-5)


def test_onnx_empty_string_and_unknown_chars_still_return_valid_scores(tiny_model_dir: Path):
    clf, _ = load_classifier(tiny_model_dir, threads=1)
    results = clf.predict_proba(["", "xyz😀", "   "])
    assert len(results) == 3
    for scores in results:
        assert_valid_scores(scores)
        assert top_class(scores) is Polarity.NEUTRAL


def test_onnx_truncates_text_to_card_max_len(tmp_path: Path):
    # max_len=3 只剩 [CLS] 好 [SEP]；沒截斷的話後面一長串「爛」會讓結果變負面
    model_dir = build_model_dir(tmp_path / "m" / "bert-test-202610210000", max_len=3)
    clf, card = load_classifier(model_dir, threads=1)
    assert card.max_len == 3
    [scores] = clf.predict_proba(["好" + "爛" * 50])
    assert top_class(scores) is Polarity.POSITIVE


def test_onnx_labels_order_in_card_decides_logit_mapping(tmp_path: Path):
    reordered = (Polarity.NEGATIVE, Polarity.NEUTRAL, Polarity.POSITIVE)
    model_dir = build_model_dir(tmp_path / "m" / "bert-test-202610210001", labels=reordered)
    clf, card = load_classifier(model_dir, threads=1)
    assert card.labels == list(reordered)
    results = clf.predict_proba([POS_TEXT, NEG_TEXT, NEU_TEXT])
    assert [top_class(s) for s in results] == [
        Polarity.POSITIVE,
        Polarity.NEGATIVE,
        Polarity.NEUTRAL,
    ]


def test_onnx_model_with_token_type_ids_input_is_fed_zeros(tmp_path: Path, tiny_model_dir: Path):
    # token type 1 的向量偏負面；全 0 時結果應與沒有該輸入的模型相同
    with_tt = build_model_dir(tmp_path / "m" / "bert-test-202610210002", with_token_type_ids=True)
    plain, _ = load_classifier(tiny_model_dir, threads=1)
    typed, _ = load_classifier(with_tt, threads=1)
    expected = plain.predict_proba([POS_TEXT])[0]
    actual = typed.predict_proba([POS_TEXT])[0]
    for polarity in Polarity:
        assert actual[polarity] == pytest.approx(expected[polarity], abs=1e-5)


def test_int8_results_stay_close_to_fp32(tiny_model_dir: Path, tiny_int8_model_dir: Path):
    fp32, _ = load_classifier(tiny_model_dir, threads=1)
    int8, _ = load_classifier(tiny_int8_model_dir, threads=1)
    texts = [POS_TEXT, NEG_TEXT, NEU_TEXT]
    for a, b in zip(fp32.predict_proba(texts), int8.predict_proba(texts), strict=True):
        assert top_class(a) is top_class(b)
        for polarity in Polarity:
            assert a[polarity] == pytest.approx(b[polarity], abs=0.1)


@pytest.mark.parametrize("threads", [1, 2])
def test_onnx_limits_intra_op_threads_to_threads_argument(
    threads: int, tiny_model_dir: Path, monkeypatch: pytest.MonkeyPatch
):
    seen: list[int] = []
    real = onnxruntime.InferenceSession

    class SpySession(real):  # type: ignore[valid-type, misc]
        def __init__(self, path_or_bytes, sess_options=None, *args, **kwargs):
            if sess_options is not None:
                seen.append(sess_options.intra_op_num_threads)
            super().__init__(path_or_bytes, sess_options, *args, **kwargs)

    monkeypatch.setattr(onnxruntime, "InferenceSession", SpySession)
    if hasattr(classifier_module, "InferenceSession"):
        monkeypatch.setattr(classifier_module, "InferenceSession", SpySession)

    clf, _ = load_classifier(tiny_model_dir, threads=threads)

    assert seen == [threads]
    assert_valid_scores(clf.predict_proba([POS_TEXT])[0])


# ---- evaluate: 耗時與記憶體峰值 ----


def test_runtime_stats_has_timing_and_memory_fields():
    names = set(evaluate.RuntimeStats.__dataclass_fields__)
    assert {
        "threads",
        "batch_size",
        "per_post_p50_ms",
        "per_post_p95_ms",
        "per_batch_p50_s",
        "per_batch_max_s",
        "peak_rss_mb",
    } <= names


def test_measure_runtime_reports_timings_memory_and_settings():
    fake = FakeClassifier()
    texts = [f"文章{i}" for i in range(10)]

    stats = evaluate.measure_runtime(fake, texts, batch_size=4, threads=2)

    assert stats.threads == 2
    assert stats.batch_size == 4
    assert stats.peak_rss_mb > 0
    assert 0 <= stats.per_post_p50_ms <= stats.per_post_p95_ms
    assert 0 <= stats.per_batch_p50_s <= stats.per_batch_max_s


def test_measure_runtime_feeds_every_text_in_batches_of_batch_size():
    fake = FakeClassifier()
    texts = [f"文章{i}" for i in range(10)]

    evaluate.measure_runtime(fake, texts, batch_size=4, threads=1)

    # 可能先暖機而多呼叫；每次呼叫不得超過 batch_size，且所有文章都推論過
    assert all(0 < len(call) <= 4 for call in fake.calls)
    assert {t for call in fake.calls for t in call} == set(texts)


def test_measure_runtime_works_with_real_onnx_classifier(tiny_model_dir: Path):
    clf, _ = load_classifier(tiny_model_dir, threads=1)

    stats = evaluate.measure_runtime(clf, [POS_TEXT, NEG_TEXT, NEU_TEXT], batch_size=2, threads=1)

    assert stats.peak_rss_mb > 0
    assert stats.per_batch_max_s >= stats.per_batch_p50_s >= 0


# ---- 骨架標記 ----


def test_no_todo_markers_for_this_task_remain():
    result = subprocess.run(
        ["grep", "-rn", "TODO(bert-classifier)", "src", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    # 排除本檔自己的字串
    lines = [ln for ln in result.stdout.splitlines() if "test_classifier_acceptance" not in ln]
    assert lines == []

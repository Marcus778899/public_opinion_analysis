import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from radar.common.enums import CommentType, CrawlReason, CrawlTaskType, Polarity
from radar.common.schemas import (
    Alert,
    CdcComment,
    CrawlTask,
    Prediction,
    RawComment,
    RawHtml,
    RawPost,
)

TAIPEI = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
POST_ID = "Stock.M.1759730000.A.1B2"


def task(**overrides):
    fields = {
        "task_id": uuid.uuid4(),
        "type": CrawlTaskType.POST,
        "board": "Stock",
        "url": "https://www.ptt.cc/bbs/Stock/M.1759730000.A.1B2.html",
        "post_id": POST_ID,
        "reason": CrawlReason.RECRAWL,
        "created_at": NOW,
    } | overrides
    return CrawlTask(**fields)


def comment(floor, type_=CommentType.PUSH, **overrides):
    fields = {
        "floor": floor,
        "type": type_,
        "user_id": "u",
        "content": "推",
        "commented_at": NOW,
    } | overrides
    return RawComment(**fields)


def post(**overrides):
    fields = {
        "task_id": uuid.uuid4(),
        "post_id": POST_ID,
        "board": "Stock",
        "url": "https://www.ptt.cc/bbs/Stock/M.1759730000.A.1B2.html",
        "author": "a",
        "title": "[新聞] 台積電",
        "content": "內文",
        "created_at": NOW,
        "crawled_at": NOW,
        "push_count": 1,
        "boo_count": 1,
        "comments": [comment(1), comment(2, CommentType.BOO), comment(3, CommentType.ARROW)],
    } | overrides
    return RawPost(**fields)


# ---------- CrawlTask ----------
def test_crawl_task_post_requires_post_id():
    with pytest.raises(ValidationError, match="requires post_id"):
        task(post_id=None)


def test_crawl_task_post_id_must_belong_to_board():
    with pytest.raises(ValidationError, match="does not belong"):
        task(board="Gossiping")


def test_crawl_task_list_rejects_post_id():
    with pytest.raises(ValidationError, match="must not carry"):
        task(type=CrawlTaskType.LIST)


def test_crawl_task_kafka_key_is_board_for_list_and_post_id_for_post():
    assert task(type=CrawlTaskType.LIST, post_id=None).kafka_key() == "Stock"
    assert task().kafka_key() == POST_ID


def test_crawl_task_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        task(created_at=datetime(2026, 10, 7, 12, 0))


# ---------- RawPost ----------
def test_raw_post_converts_times_to_utc():
    taipei_noon = datetime(2026, 10, 7, 20, 0, tzinfo=TAIPEI)

    p = post(created_at=taipei_noon, crawled_at=taipei_noon)

    assert p.created_at == NOW
    assert p.created_at.tzinfo == UTC
    assert p.crawled_at.tzinfo == UTC


def test_raw_post_rejects_naive_datetime():
    with pytest.raises(ValidationError):
        post(created_at=datetime(2026, 10, 7, 12, 0))


def test_raw_post_post_id_must_belong_to_board():
    with pytest.raises(ValidationError, match="does not belong"):
        post(board="Gossiping")


def test_raw_post_rejects_duplicate_floor():
    with pytest.raises(ValidationError, match="duplicate comment floors"):
        post(comments=[comment(1), comment(1, CommentType.BOO)])


def test_raw_post_counts_must_match_comments():
    with pytest.raises(ValidationError, match="counts mismatch"):
        post(push_count=5)


def test_raw_post_without_comments_needs_zero_counts():
    assert post(push_count=0, boo_count=0, comments=[]).comments == []


def test_raw_post_rejects_negative_counts():
    with pytest.raises(ValidationError):
        post(push_count=-1)


def test_raw_post_json_roundtrip_keeps_chinese_text():
    original = post()

    restored = RawPost.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.title == "[新聞] 台積電"


def test_raw_post_ignores_unknown_fields_for_forward_compat():
    payload = json.loads(post().model_dump_json()) | {"new_field": 1, "schema_version": 2}

    assert RawPost.model_validate(payload).schema_version == 2


def test_raw_post_deleted_post_allows_missing_content():
    p = post(is_deleted=True, author=None, title=None, content=None)

    assert p.is_deleted


# ---------- RawComment / RawHtml ----------
def test_raw_comment_floor_starts_at_one():
    with pytest.raises(ValidationError):
        comment(0)


def test_raw_comment_allows_missing_time():
    assert comment(1, commented_at=None).commented_at is None


def test_raw_comment_converts_time_to_utc():
    c = comment(1, commented_at=datetime(2026, 10, 7, 20, 0, tzinfo=TAIPEI))

    assert c.commented_at == NOW


def test_raw_comment_rejects_unknown_type():
    with pytest.raises(ValidationError):
        comment(1, type_="like")


def test_raw_html_roundtrip():
    html = RawHtml(post_id=POST_ID, url="u", crawled_at=NOW, html="<html>推</html>")

    assert RawHtml.model_validate_json(html.model_dump_json()) == html


TEXT_HASH = "a" * 64


def prediction(**overrides):
    fields = {
        "post_id": POST_ID,
        "model_version": "tfidf-lr-20261016T0300",
        "predicted_at": NOW,
        "polarity": "negative",
        "scores": {"positive": 0.1, "negative": 0.7, "neutral": 0.2},
        "text_hash": TEXT_HASH,
    }
    return Prediction(**{**fields, **overrides})


def test_prediction_valid_scores_accepted():
    p = prediction()

    assert p.polarity is Polarity.NEGATIVE
    assert p.scores[Polarity.NEUTRAL] == 0.2


def test_prediction_missing_polarity_key_rejected():
    with pytest.raises(ValidationError, match="exactly"):
        prediction(scores={"negative": 0.8, "neutral": 0.2})


def test_prediction_scores_not_summing_to_one_rejected():
    with pytest.raises(ValidationError, match="sum to 1"):
        prediction(scores={"positive": 0.1, "negative": 0.7, "neutral": 0.5})


def test_prediction_polarity_not_highest_score_rejected():
    with pytest.raises(ValidationError, match="not the highest"):
        prediction(polarity="positive")


def test_prediction_tied_highest_score_accepted():
    prediction(polarity="neutral", scores={"positive": 0.2, "negative": 0.4, "neutral": 0.4})


def test_prediction_json_matches_spec_3_5():
    data = json.loads(prediction().model_dump_json())

    assert data == {
        "schema_version": 1,
        "post_id": POST_ID,
        "model_version": "tfidf-lr-20261016T0300",
        "predicted_at": "2026-10-07T12:00:00Z",
        "polarity": "negative",
        "scores": {"positive": 0.1, "negative": 0.7, "neutral": 0.2},
        "text_hash": TEXT_HASH,
    }


@pytest.mark.parametrize("bad", ["", "a" * 63, "A" * 64, "g" * 64])
def test_prediction_text_hash_not_sha256_hex_rejected(bad):
    with pytest.raises(ValidationError, match="text_hash"):
        prediction(text_hash=bad)


def test_prediction_missing_text_hash_rejected():
    fields = prediction().model_dump(exclude={"text_hash"})

    with pytest.raises(ValidationError, match="text_hash"):
        Prediction(**fields)


# --- CdcComment ---


def test_cdc_comment_parses_debezium_flattened_record():
    c = CdcComment.model_validate(
        {
            "post_id": POST_ID,
            "floor": 3,
            "type": "push",
            "user_id": "u",
            "content": "c",
            "commented_at": "2026-10-16T02:03:00Z",
            "__op": "c",
            "__source_ts_ms": 1792116180000,
            "__deleted": "false",
        }
    )

    assert (c.floor, c.type, c.op, c.deleted) == (3, CommentType.PUSH, "c", "false")
    assert c.commented_at == datetime(2026, 10, 16, 2, 3, tzinfo=UTC)
    assert c.source_ts_ms == 1792116180000


def test_cdc_comment_without_commented_at_accepted():
    c = CdcComment.model_validate({"post_id": POST_ID, "floor": 1, "type": "arrow", "__op": "c"})

    assert c.commented_at is None


def test_cdc_comment_unknown_type_rejected():
    with pytest.raises(ValidationError):
        CdcComment.model_validate({"post_id": POST_ID, "floor": 1, "type": "like"})


# --- Alert ---


def alert(**overrides):
    fields = {
        "alert_id": uuid.UUID(int=1),
        "unit_type": "post",
        "unit_key": POST_ID,
        "board": "Stock",
        "window_start": NOW - timedelta(minutes=10),
        "window_end": NOW,
        "value": 85,
        "baseline": 6.2,
        "zscore": 7.4,
        "sample_post_ids": [POST_ID],
        "created_at": NOW,
    }
    return Alert(**{**fields, **overrides})


def test_alert_json_matches_spec_3_6():
    data = json.loads(alert().model_dump_json())

    assert data == {
        "schema_version": 1,
        "alert_id": "00000000-0000-0000-0000-000000000001",
        "unit_type": "post",
        "unit_key": POST_ID,
        "board": "Stock",
        "window_start": "2026-10-07T11:50:00Z",
        "window_end": "2026-10-07T12:00:00Z",
        "value": 85,
        "baseline": 6.2,
        "zscore": 7.4,
        "sample_post_ids": [POST_ID],
        "created_at": "2026-10-07T12:00:00Z",
    }


def test_alert_unit_type_outside_mvp_rejected():
    with pytest.raises(ValidationError):
        alert(unit_type="entity")


def test_alert_negative_value_rejected():
    with pytest.raises(ValidationError):
        alert(value=-1)


def test_post_task_rejects_backfill_fields():
    base = {
        "task_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
        "type": "post",
        "board": "Stock",
        "url": "https://www.ptt.cc/bbs/Stock/M.1.A.001.html",
        "post_id": "Stock.M.1.A.001",
        "reason": "recrawl",
        "created_at": "2026-10-29T00:00:00Z",
    }
    for extra in ({"backfill_depth": 1}, {"since": "2026-10-29T00:00:00Z"}, {"reason": "backfill"}):
        with pytest.raises(ValidationError):
            CrawlTask.model_validate({**base, **extra})

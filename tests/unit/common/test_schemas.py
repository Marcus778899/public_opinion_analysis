import json
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from radar.common.enums import CommentType, CrawlReason, CrawlTaskType
from radar.common.schemas import CrawlTask, RawComment, RawHtml, RawPost

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

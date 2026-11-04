"""開發規格 3.1、7.28 A：crawl.tasks 的 since、backfill_depth、reason=backfill。"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.schemas import CrawlTask
from radar.common.tasks import make_list_task

NOW = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
SINCE = datetime(2026, 10, 29, 4, 50, tzinfo=UTC)
LIST_URL = "https://www.ptt.cc/bbs/Gossiping/index100.html"
POST_URL = "https://www.ptt.cc/bbs/Gossiping/M.1791345103.A.E41.html"


def list_payload(**over):
    base = {
        "task_id": str(uuid.uuid4()),
        "type": "list",
        "board": "Gossiping",
        "url": LIST_URL,
        "reason": "schedule",
        "created_at": NOW.isoformat(),
    }
    return {**base, **over}


def post_payload(**over):
    base = {
        **list_payload(),
        "type": "post",
        "url": POST_URL,
        "post_id": "Gossiping.M.1791345103.A.E41",
        "reason": "recrawl",
    }
    return {**base, **over}


def test_crawl_reason_has_backfill_value():
    assert CrawlReason("backfill") is CrawlReason.BACKFILL


def test_list_task_without_new_fields_defaults_to_null_and_zero():
    task = CrawlTask.model_validate(list_payload())

    assert task.since is None
    assert task.backfill_depth == 0


def test_backfill_list_task_carries_since_and_depth():
    task = CrawlTask.model_validate(
        list_payload(reason="backfill", since=SINCE.isoformat(), backfill_depth=3)
    )

    assert task.reason is CrawlReason.BACKFILL
    assert task.since == SINCE
    assert task.backfill_depth == 3
    assert task.type is CrawlTaskType.LIST


def test_backfill_task_json_round_trip_keeps_fields():
    task = CrawlTask.model_validate(
        list_payload(reason="backfill", since=SINCE.isoformat(), backfill_depth=6)
    )

    data = json.loads(task.model_dump_json())

    assert data["since"] is not None
    assert data["backfill_depth"] == 6
    assert data["reason"] == "backfill"
    assert data["schema_version"] == 1
    assert CrawlTask.model_validate_json(task.model_dump_json()) == task


def test_since_with_offset_is_converted_to_utc():
    task = CrawlTask.model_validate(list_payload(since="2026-10-29T12:50:00+08:00"))

    assert task.since == SINCE
    assert task.since.utcoffset() == timedelta(0)


def test_since_without_timezone_is_rejected():
    with pytest.raises(ValidationError):
        CrawlTask.model_validate(list_payload(since="2026-10-29T04:50:00"))


def test_negative_backfill_depth_is_rejected():
    with pytest.raises(ValidationError):
        CrawlTask.model_validate(list_payload(backfill_depth=-1))


@pytest.mark.parametrize(
    "extra",
    [
        {"since": SINCE.isoformat()},
        {"backfill_depth": 1},
        {"reason": "backfill"},
    ],
    ids=["since", "backfill_depth", "reason_backfill"],
)
def test_post_task_with_list_only_fields_is_rejected(extra):
    with pytest.raises(ValidationError):
        CrawlTask.model_validate(post_payload(**extra))


def test_post_task_with_defaults_is_still_valid():
    task = CrawlTask.model_validate(post_payload())

    assert (task.since, task.backfill_depth) == (None, 0)


def test_backfill_list_task_key_is_board():
    task = CrawlTask.model_validate(
        list_payload(reason="backfill", since=SINCE.isoformat(), backfill_depth=3)
    )

    assert task.kafka_key() == "Gossiping"


def test_make_list_task_defaults_have_no_since():
    task = make_list_task("Gossiping", CrawlReason.SCHEDULE, NOW)

    assert (task.since, task.backfill_depth) == (None, 0)


def test_make_list_task_passes_since_through():
    task = make_list_task("Gossiping", CrawlReason.SCHEDULE, NOW, since=SINCE)

    assert task.since == SINCE
    assert task.reason is CrawlReason.SCHEDULE
    assert task.backfill_depth == 0
    assert task.type is CrawlTaskType.LIST


def test_make_list_task_manual_without_since_stays_null():
    task = make_list_task("Gossiping", CrawlReason.MANUAL, NOW)

    assert task.since is None

import json
from datetime import UTC, datetime

import httpx2
import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from radar.api.schemas import BoardOut
from radar.collector.scheduler import (
    BOARD_JOB_PREFIX,
    BoardsClient,
    enabled_board_names,
    make_list_task_sender,
    sync_board_jobs,
)
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings
from tests.unit.common.kafka.fakes import FakeProducer

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def board(name="Stock", *, enabled=True, interval_sec=120):
    return BoardOut(
        board=name, enabled=enabled, interval_sec=interval_sec, recrawl_min_push=0, updated_at=NOW
    )


@pytest.fixture
def scheduler():
    # 不啟動，只檢查計時器的增減與設定
    sched = BackgroundScheduler(timezone=UTC)
    yield sched


def noop(board_name: str) -> None:
    pass


def board_jobs(scheduler):
    return {j.id: j for j in scheduler.get_jobs() if j.id.startswith(BOARD_JOB_PREFIX)}


def test_sync_adds_job_for_enabled_board(scheduler):
    sync_board_jobs(scheduler, [board("Stock", interval_sec=120)], noop)

    job = board_jobs(scheduler)["board:Stock"]
    assert job.trigger.interval.total_seconds() == 120
    assert job.args == ("Stock",)


def test_sync_removes_job_for_disabled_board(scheduler):
    sync_board_jobs(scheduler, [board("Stock")], noop)

    sync_board_jobs(scheduler, [board("Stock", enabled=False)], noop)

    assert board_jobs(scheduler) == {}


def test_sync_removes_job_for_board_missing_from_api(scheduler):
    sync_board_jobs(scheduler, [board("Stock"), board("Tech_Job")], noop)

    sync_board_jobs(scheduler, [board("Stock")], noop)

    assert set(board_jobs(scheduler)) == {"board:Stock"}


def test_sync_reschedules_when_interval_changes(scheduler):
    sync_board_jobs(scheduler, [board("Stock", interval_sec=120)], noop)

    sync_board_jobs(scheduler, [board("Stock", interval_sec=300)], noop)

    assert board_jobs(scheduler)["board:Stock"].trigger.interval.total_seconds() == 300


def test_sync_no_change_keeps_job_untouched(scheduler):
    sync_board_jobs(scheduler, [board("Stock")], noop)
    before = board_jobs(scheduler)["board:Stock"]

    sync_board_jobs(scheduler, [board("Stock")], noop)

    after = board_jobs(scheduler)["board:Stock"]
    assert after.trigger is before.trigger
    assert after.next_run_time == before.next_run_time


def test_sync_ignores_non_board_jobs(scheduler):
    scheduler.add_job(noop, "interval", seconds=30, id="due_posts", args=["x"])

    sync_board_jobs(scheduler, [], noop)

    assert scheduler.get_job("due_posts") is not None


def client_with(handler) -> BoardsClient:
    return BoardsClient("http://api:8000", transport=httpx2.MockTransport(handler))


def test_boards_client_parses_boards():
    payload = [json.loads(board("Stock").model_dump_json())]

    result = client_with(lambda r: httpx2.Response(200, json=payload)).fetch()

    assert result == [board("Stock")]


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx2.Response(500),
        lambda r: httpx2.Response(200, text="not json"),
        lambda r: httpx2.Response(200, json=[{"board": "x"}]),
    ],
)
def test_boards_client_returns_none_on_error(handler):
    assert client_with(handler).fetch() is None


def test_boards_client_returns_none_on_connection_error():
    def refuse(request):
        raise httpx2.ConnectError("refused", request=request)

    assert client_with(refuse).fetch() is None


def test_list_task_sender_sends_schedule_task_keyed_by_board():
    fake = FakeProducer()
    send = make_list_task_sender(
        JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake), lambda: []
    )

    send("Gossiping")

    [message] = fake.produced
    task = json.loads(message["value"])
    assert (message["topic"], message["key"]) == (names.CRAWL_TASKS, b"Gossiping")
    assert (task["type"], task["reason"]) == ("list", "schedule")
    assert fake._pending == []


def test_list_task_sender_swallows_kafka_error():
    fake = FakeProducer(fail_delivery=True)
    send = make_list_task_sender(
        JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake), lambda: []
    )

    send("Stock")  # 不拋例外，計時器才不會停掉


INITIAL = ["Gossiping", "Stock", "Tech_Job"]


def sender_with(fake: FakeProducer, enabled: list[str]):
    return make_list_task_sender(
        JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake), lambda: enabled
    )


def test_list_task_sender_initial_boards_go_to_distinct_partitions():
    fake = FakeProducer(topic_partitions={names.CRAWL_TASKS: 3})
    send = sender_with(fake, INITIAL)

    for b in INITIAL:
        send(b)

    assert [(m["key"], m["partition"]) for m in fake.produced] == [
        (b"Gossiping", 0),
        (b"Stock", 1),
        (b"Tech_Job", 2),
    ]


def test_list_task_sender_unsynced_board_falls_back_to_key_hash():
    fake = FakeProducer(topic_partitions={names.CRAWL_TASKS: 3})

    sender_with(fake, INITIAL)("NewBoard")

    assert "partition" not in fake.produced[0]


def test_list_task_sender_partition_count_failure_falls_back_to_key_hash():
    fake = FakeProducer()  # crawl.tasks 查不到 metadata

    sender_with(fake, INITIAL)("Stock")

    [message] = fake.produced
    assert message["key"] == b"Stock"
    assert "partition" not in message


def test_enabled_board_names_keeps_only_enabled():
    boards = [board("Stock"), board("Gossiping", enabled=False), board("Tech_Job")]

    assert enabled_board_names(boards) == ["Stock", "Tech_Job"]

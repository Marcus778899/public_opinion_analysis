import json
from datetime import UTC, datetime, timedelta

import pytest

from radar.collector import recrawl
from radar.collector.recrawl import DuePost, DuePostDispatcher, next_crawl_at
from radar.common.kafka import names
from radar.common.kafka.producer import DeliveryError, JsonProducer
from radar.common.settings import KafkaSettings
from tests.unit.common.kafka.fakes import FakeProducer

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def created(age: timedelta) -> datetime:
    return NOW - age


@pytest.mark.parametrize("age_minutes", [0, 30, 59])
def test_next_crawl_under_1h_is_2_minutes(age_minutes):
    assert next_crawl_at(created(timedelta(minutes=age_minutes)), NOW) == NOW + timedelta(minutes=2)


@pytest.mark.parametrize("age_hours", [1, 3, 5.9])
def test_next_crawl_1h_to_6h_is_10_minutes(age_hours):
    assert next_crawl_at(created(timedelta(hours=age_hours)), NOW) == NOW + timedelta(minutes=10)


@pytest.mark.parametrize("age_hours", [6, 12, 23.9])
def test_next_crawl_6h_to_24h_is_1_hour(age_hours):
    assert next_crawl_at(created(timedelta(hours=age_hours)), NOW) == NOW + timedelta(hours=1)


@pytest.mark.parametrize("age_hours", [24, 48])
def test_next_crawl_over_24h_stops(age_hours):
    assert next_crawl_at(created(timedelta(hours=age_hours)), NOW) is None


def test_next_crawl_time_scale_shrinks_interval():
    result = next_crawl_at(created(timedelta(minutes=5)), NOW, time_scale=0.05)

    assert result == NOW + timedelta(seconds=6)


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def session():
    return FakeSession()


def due(n: int) -> list[DuePost]:
    return [
        DuePost(f"Stock.{name}", "Stock", f"https://www.ptt.cc/bbs/Stock/{name}.html", NOW)
        for name in (f"M.{i}.A.00{i}" for i in range(1, n + 1))
    ]


def make_dispatcher(session, producer, monkeypatch, posts, recorded):
    monkeypatch.setattr(recrawl, "find_due_posts", lambda s, now, limit: posts[:limit])
    monkeypatch.setattr(
        recrawl, "record_dispatch", lambda s, p, now, time_scale: recorded.extend(p)
    )
    json_producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer)
    return DuePostDispatcher(lambda: session, json_producer, limit=2, time_scale=1.0)


def test_dispatcher_sends_post_tasks_then_records_state(session, monkeypatch):
    producer, recorded = FakeProducer(), []
    dispatcher = make_dispatcher(session, producer, monkeypatch, due(3), recorded)

    assert dispatcher(NOW) == 2

    assert [m["key"] for m in producer.produced] == [b"Stock.M.1.A.001", b"Stock.M.2.A.002"]
    task = json.loads(producer.produced[0]["value"])
    assert (task["type"], task["reason"], task["post_id"]) == ("post", "recrawl", "Stock.M.1.A.001")
    assert {m["topic"] for m in producer.produced} == {names.CRAWL_TASKS}
    assert len(recorded) == 2
    assert session.commits == 1


def test_dispatcher_kafka_failure_does_not_record_state(session, monkeypatch):
    producer, recorded = FakeProducer(fail_delivery=True), []
    dispatcher = make_dispatcher(session, producer, monkeypatch, due(1), recorded)

    with pytest.raises(DeliveryError):
        dispatcher(NOW)

    assert recorded == []
    assert session.commits == 0


def test_dispatcher_nothing_due_sends_nothing(session, monkeypatch):
    producer, recorded = FakeProducer(), []
    dispatcher = make_dispatcher(session, producer, monkeypatch, [], recorded)

    assert dispatcher(NOW) == 0
    assert producer.produced == []
    assert session.commits == 0

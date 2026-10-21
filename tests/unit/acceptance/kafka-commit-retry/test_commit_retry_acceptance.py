"""驗收 kafka-commit-retry（開發規格 2.2）：commit 遇暫時性錯誤退避重試。

只走 BatchConsumer.run() 的對外行為；Kafka consumer 換成 fake。
"""

import itertools
import json
import sys
from pathlib import Path

import pytest
from confluent_kafka import KafkaError, KafkaException
from pydantic import BaseModel

# NOTE: 目錄名含連字號，不能放 __init__.py，rootdir 不在 sys.path；補上才能重用 fakes
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from tests.unit.common.kafka.fakes import (
    FakeClock,
    FakeConsumer,
    FakeError,
    FakeMessage,
    FakeProducer,
)

from radar.common.kafka import consumer as consumer_module  # noqa: E402
from radar.common.kafka.consumer import BatchConsumer
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings

SETTINGS = KafkaSettings(bootstrap_servers="unused:9092")

RETRIABLE = [
    KafkaError.COORDINATOR_LOAD_IN_PROGRESS,
    KafkaError.COORDINATOR_NOT_AVAILABLE,
    KafkaError.NOT_COORDINATOR,
]


class Event(BaseModel):
    id: int


class RecordingLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _add(self, level: str, msg: object, *args: object) -> None:
        text = str(msg)
        try:
            text = text % args if args else text
        except (TypeError, ValueError):
            text = f"{text} {args}"
        self.records.append((level, text))

    def debug(self, msg, *a, **k):
        self._add("DEBUG", msg, *a)

    def info(self, msg, *a, **k):
        self._add("INFO", msg, *a)

    def warning(self, msg, *a, **k):
        self._add("WARNING", msg, *a)

    warn = warning

    def error(self, msg, *a, **k):
        self._add("ERROR", msg, *a)

    def critical(self, msg, *a, **k):
        self._add("CRITICAL", msg, *a)

    def exception(self, msg, *a, **k):
        self._add("ERROR", msg, *a)


@pytest.fixture
def recorded(monkeypatch) -> RecordingLog:
    rec = RecordingLog()
    monkeypatch.setattr(consumer_module, "log", rec)
    return rec


def msg(event_id: int) -> FakeMessage:
    return FakeMessage(json.dumps({"id": event_id}).encode(), offset_=event_id)


def kafka_error(code: int) -> KafkaException:
    return KafkaException(FakeError(code))


def build(batches, handler, backoff=None):
    clock = FakeClock()
    fake = FakeConsumer(batches=batches, clock=clock)
    dlq = DlqPublisher(JsonProducer(SETTINGS, producer=FakeProducer()), "test")
    consumer = BatchConsumer(
        SETTINGS,
        group_id="g",
        topics=["in"],
        model=Event,
        handler=handler,
        dlq=dlq,
        consumer=fake,
        backoff=backoff or (lambda: itertools.repeat(0)),
        clock=clock,
    )
    fake.on_exhausted = consumer.stop
    return consumer, fake


@pytest.mark.parametrize("code", RETRIABLE)
def test_commit_retriable_error_is_retried_then_consumption_continues(code):
    handled = []
    consumer, fake = build([[msg(1)], [msg(2)]], handled.append)
    fake.commit_errors = [kafka_error(code), kafka_error(code)]

    consumer.run()

    assert handled == [[Event(id=1)], [Event(id=2)]]  # 重試 commit 不可重跑 handler
    assert fake.commits == 2
    assert fake.closed


def test_commit_retry_uses_backoff_delays():
    asked = []

    def backoff():
        for d in itertools.repeat(0.0):
            asked.append(d)
            yield d

    consumer, fake = build([[msg(1)]], lambda items: None, backoff=backoff)
    fake.commit_errors = [kafka_error(KafkaError.COORDINATOR_LOAD_IN_PROGRESS)] * 2

    consumer.run()

    assert fake.commits == 1
    assert len(asked) >= 2


def test_commit_retry_stops_when_stop_requested_without_committing():
    consumer, fake = build([[msg(1)]], lambda items: None)

    def stopping_backoff():
        consumer.stop()
        yield from itertools.repeat(0.0)

    consumer._backoff = stopping_backoff  # noqa: SLF001 - 只為在重試期間送出停止訊號
    fake.commit_errors = [kafka_error(KafkaError.COORDINATOR_LOAD_IN_PROGRESS)] * 3

    consumer.run()  # 不得拋出

    assert fake.commits == 0
    assert fake.closed


def test_commit_retriable_error_beyond_limit_raises():
    consumer, fake = build([[msg(1)]], lambda items: None)
    errors = [kafka_error(KafkaError.COORDINATOR_NOT_AVAILABLE) for _ in range(1000)]
    fake.commit_errors = errors

    with pytest.raises(KafkaException):
        consumer.run()

    assert fake.commits == 0
    assert fake.closed
    assert len(errors) > 0  # 有上限：沒有無限重試到錯誤用完


def test_commit_non_retriable_error_raises_without_retry():
    consumer, fake = build([[msg(1)]], lambda items: None)
    errors = [kafka_error(KafkaError._TRANSPORT) for _ in range(5)]
    fake.commit_errors = errors

    with pytest.raises(KafkaException):
        consumer.run()

    assert len(errors) == 4  # 只消耗一個，沒有重試
    assert fake.closed


@pytest.mark.parametrize("code", [KafkaError._ASSIGNMENT_LOST, KafkaError.UNKNOWN_MEMBER_ID])
def test_commit_assignment_lost_still_warns_without_retry(code, recorded):
    handled = []
    consumer, fake = build([[msg(1)], [msg(2)]], handled.append)
    errors = [kafka_error(code)]
    fake.commit_errors = errors

    consumer.run()

    assert len(handled) == 2
    assert errors == []  # 只 commit 失敗一次，沒有重試
    assert fake.commits == 1
    assert any(level == "WARNING" for level, _ in recorded.records)


@pytest.mark.parametrize("code", RETRIABLE)
def test_each_retry_logs_one_warning_with_code_and_attempt(code, recorded):
    consumer, fake = build([[msg(1)]], lambda items: None)
    fake.commit_errors = [kafka_error(code), kafka_error(code)]

    consumer.run()

    warnings = [text for level, text in recorded.records if level == "WARNING"]
    assert len(warnings) == 2
    assert all(str(code) in text for text in warnings)
    assert "1" in warnings[0]
    assert "2" in warnings[1]

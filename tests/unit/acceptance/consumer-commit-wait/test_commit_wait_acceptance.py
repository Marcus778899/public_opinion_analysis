"""驗收 consumer-commit-wait（#146）：commit 重試等待改成分段 sleep，不用 Event.wait。

sleep 以 `sleep=` 建構參數注入，clock 沿用 `clock=`；測試不真的等待。
"""

import itertools
import json
import subprocess
import sys
import threading
from pathlib import Path

from confluent_kafka import KafkaError, KafkaException
from pydantic import BaseModel

# NOTE: 目錄名含連字號，不能放 __init__.py；補上 rootdir 才能重用 fakes
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from tests.unit.common.kafka.fakes import (  # noqa: E402
    FakeClock,
    FakeConsumer,
    FakeError,
    FakeMessage,
    FakeProducer,
)

from radar.common.kafka.consumer import BatchConsumer  # noqa: E402
from radar.common.kafka.dlq import DlqPublisher  # noqa: E402
from radar.common.kafka.producer import JsonProducer  # noqa: E402
from radar.common.settings import KafkaSettings  # noqa: E402

SETTINGS = KafkaSettings(bootstrap_servers="unused:9092")
MAX_SEGMENT_S = 0.5


class Event(BaseModel):
    id: int


def retriable() -> KafkaException:
    return KafkaException(FakeError(KafkaError.COORDINATOR_NOT_AVAILABLE))


def build(delay: float, on_sleep=None):
    """回傳 consumer、fake、sleeps；fake sleep 只推進 clock 並記錄秒數。"""
    clock = FakeClock()
    fake = FakeConsumer(
        batches=[[FakeMessage(json.dumps({"id": 1}).encode(), offset_=1)]], clock=clock
    )
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        clock.t += seconds
        if on_sleep:
            on_sleep(len(sleeps))

    dlq = DlqPublisher(JsonProducer(SETTINGS, producer=FakeProducer()), "test")
    consumer = BatchConsumer(
        SETTINGS,
        group_id="g",
        topics=["in"],
        model=Event,
        handler=lambda items: None,
        dlq=dlq,
        consumer=fake,
        backoff=lambda: itertools.repeat(delay),
        clock=clock,
        sleep=fake_sleep,
    )
    fake.on_exhausted = consumer.stop
    return consumer, fake, sleeps


def test_stop_during_commit_wait_ends_within_one_segment_without_commit():
    holder = {}

    def on_sleep(n: int) -> None:
        if n == 2:
            holder["consumer"].stop()

    consumer, fake, sleeps = build(delay=30.0, on_sleep=on_sleep)
    holder["consumer"] = consumer
    fake.commit_errors = [retriable()] * 3

    consumer.run()  # 不可拋出

    assert fake.commits == 0
    assert fake.closed
    assert len(sleeps) == 2  # 停止後不再多睡一段
    assert all(0 < s <= MAX_SEGMENT_S for s in sleeps)


def test_commit_wait_is_split_into_segments_and_then_retries_commit():
    consumer, fake, sleeps = build(delay=1.2)
    fake.commit_errors = [retriable()]

    consumer.run()

    assert fake.commits == 1
    assert len(sleeps) >= 3
    assert all(0 < s <= MAX_SEGMENT_S for s in sleeps)
    assert abs(sum(sleeps) - 1.2) < 1e-6


def test_zero_delay_commit_retry_does_not_sleep():
    consumer, fake, sleeps = build(delay=0.0)
    fake.commit_errors = [retriable()]

    consumer.run()

    assert fake.commits == 1
    assert sleeps == []


def test_commit_wait_never_calls_event_wait(monkeypatch):
    def boom(self, timeout=None):
        raise AssertionError("Event.wait 不可用於 commit 重試等待")

    monkeypatch.setattr(threading.Event, "wait", boom)
    consumer, fake, _ = build(delay=1.0)
    fake.commit_errors = [retriable()]

    consumer.run()

    assert fake.commits == 1


def test_source_has_no_stop_wait_call():
    result = subprocess.run(
        ["grep", "-rn", "_stop.wait", str(ROOT / "src" / "radar")],
        capture_output=True,
        text=True,
    )
    assert result.stdout == ""

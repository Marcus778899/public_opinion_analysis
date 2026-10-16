import itertools
import json

import pytest
from confluent_kafka import KafkaError, KafkaException, TopicPartition
from pydantic import BaseModel

from radar.common.kafka.consumer import BatchConsumer, DecodeError, Rejection, TransientError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings
from tests.unit.common.kafka.fakes import (
    PARTITION_EOF,
    FakeClock,
    FakeConsumer,
    FakeError,
    FakeMessage,
    FakeProducer,
)

SETTINGS = KafkaSettings(bootstrap_servers="unused:9092")


class Event(BaseModel):
    id: int


def msg(event_id: int, offset: int = 0) -> FakeMessage:
    return FakeMessage(json.dumps({"id": event_id}).encode(), offset_=offset)


def build(batches, handler, dlq_producer=None, decode=None, backoff=None):
    clock = FakeClock()
    fake = FakeConsumer(batches=batches, clock=clock)
    dlq_producer = dlq_producer or FakeProducer()
    dlq = DlqPublisher(JsonProducer(SETTINGS, producer=dlq_producer), "test")
    consumer = BatchConsumer(
        SETTINGS,
        group_id="g",
        topics=["in"],
        model=Event,
        handler=handler,
        dlq=dlq,
        consumer=fake,
        backoff=backoff or (lambda: itertools.repeat(0)),
        decode=decode,
        clock=clock,
    )
    fake.on_exhausted = consumer.stop
    return consumer, fake, dlq_producer


def test_subscribes_to_topics():
    _, fake, _ = build([], lambda items: None)

    assert fake.subscribed == ["in"]


def test_valid_batch_is_handled_then_committed():
    handled = []
    consumer, fake, _ = build([[msg(1), msg(2)]], handled.append)

    consumer.run()

    assert handled == [[Event(id=1), Event(id=2)]]
    assert fake.commits == 1
    assert fake.closed


def test_undecodable_message_goes_to_dlq_and_rest_are_handled():
    handled = []
    consumer, fake, dlq_producer = build([[msg(1), FakeMessage(b"not json")]], handled.append)

    consumer.run()

    assert handled == [[Event(id=1)]]
    assert len(dlq_producer.produced) == 1
    assert fake.commits == 1


def test_all_messages_invalid_skips_handler_but_commits():
    handled = []
    consumer, fake, _ = build([[FakeMessage(b"{}")]], handled.append)

    consumer.run()

    assert handled == []
    assert fake.commits == 1


def test_transient_error_then_success_commits_once():
    calls = []

    def handler(items):
        calls.append(items)
        if len(calls) < 3:
            raise TransientError("db down")

    consumer, fake, _ = build([[msg(1)]], handler)

    consumer.run()

    assert len(calls) == 3
    assert fake.commits == 1


def test_stop_during_retry_leaves_batch_uncommitted():
    def handler(items):
        consumer.stop()
        raise TransientError("db down")

    consumer, fake, _ = build([[msg(1)]], handler)

    consumer.run()

    assert fake.commits == 0
    assert fake.closed


def test_unexpected_error_propagates_without_commit():
    def handler(items):
        raise RuntimeError("bug")

    consumer, fake, _ = build([[msg(1)]], handler)

    with pytest.raises(RuntimeError):
        consumer.run()
    assert fake.commits == 0
    assert fake.closed


def test_stop_finishes_current_batch_then_closes():
    handled = []

    def handler(items):
        handled.append(items)
        consumer.stop()

    consumer, fake, _ = build([[msg(1)], [msg(2)]], handler)

    consumer.run()

    assert handled == [[Event(id=1)]]
    assert fake.commits == 1


def test_empty_poll_does_not_call_handler_or_commit():
    handled = []
    consumer, fake, _ = build([[]], handled.append)

    consumer.run()

    assert handled == []
    assert fake.commits == 0


def test_partition_eof_is_ignored():
    handled = []
    eof = FakeMessage(None, error_=PARTITION_EOF)
    consumer, _, _ = build([[eof, msg(1)]], handled.append)

    consumer.run()

    assert handled == [[Event(id=1)]]


def test_fatal_broker_error_raises():
    fatal = FakeMessage(None, error_=FakeError(KafkaError._FATAL, fatal=True))
    consumer, fake, _ = build([[fatal]], lambda items: None)

    with pytest.raises(KafkaException):
        consumer.run()
    assert fake.closed


def test_custom_decode_is_used_and_decode_error_goes_to_dlq():
    def decode(message) -> Event:
        if message.value() == b"bad":
            raise DecodeError("broken avro")
        return Event(id=int(message.value()))

    handled = []
    batches = [[FakeMessage(b"bad"), FakeMessage(b"7")]]
    consumer, fake, dlq_producer = build(batches, handled.append, decode=decode)

    consumer.run()

    assert handled == [[Event(id=7)]]
    assert len(dlq_producer.produced) == 1
    assert fake.commits == 1


# --- #11：重試期間維持成員資格、commit 失去 assignment 不中止 ---


def fail_times(n: int, error: TransientError | None = None):
    """前 n 次拋 TransientError，之後成功；回傳 (handler, calls)。"""
    calls = []

    def handler(items):
        calls.append(items)
        if len(calls) <= n:
            raise error or TransientError("down")

    return handler, calls


def lost(code: int) -> KafkaException:
    return KafkaException(FakeError(code))


def test_retry_pauses_assigned_partitions_and_resumes_after_success():
    paused_during_retry = []
    handler, _ = fail_times(1)

    def spy(items):
        paused_during_retry.append(set(fake.paused))
        handler(items)

    consumer, fake, _ = build([[msg(1)]], spy)

    consumer.run()

    assert paused_during_retry == [set(), {("in", 0)}]
    assert fake.paused == set()
    assert (fake.pause_calls, fake.resume_calls) == (1, 1)
    assert fake.commits == 1


def test_retry_wait_keeps_polling_instead_of_sleeping():
    handler, _ = fail_times(1)
    consumer, fake, _ = build([[msg(1)]], handler, backoff=lambda: itertools.repeat(3.5))

    consumer.run()

    # 3.5 秒的等待拆成每次最多 1 秒的 poll
    assert fake.polls == [1.0, 1.0, 1.0, 0.5]


def test_message_polled_while_paused_is_seeked_back_not_dropped():
    handler, calls = fail_times(1)
    consumer, fake, _ = build([[msg(1)]], handler, backoff=lambda: itertools.repeat(2))
    fake.poll_results = [FakeMessage(b'{"id": 9}', partition_=1, offset_=42)]

    consumer.run()

    assert fake.seeks == [("in", 1, 42)]
    assert calls == [[Event(id=1)], [Event(id=1)]]


def test_partitions_assigned_during_retry_are_paused():
    new = [TopicPartition("in", 2)]
    paused_after_rebalance = []
    handler, _ = fail_times(1)
    consumer, fake, _ = build([[msg(1)]], handler, backoff=lambda: itertools.repeat(1))
    original_poll = fake.poll

    def poll_with_rebalance(timeout=-1):
        fake.on_assign(fake, new)  # 重試等待期間發生 rebalance
        paused_after_rebalance.append(set(fake.paused))
        return original_poll(timeout)

    fake.poll = poll_with_rebalance

    consumer.run()

    assert fake.assigned == new
    assert paused_after_rebalance == [{("in", 0), ("in", 2)}]


def test_partitions_assigned_while_not_retrying_are_not_paused():
    consumer, fake, _ = build([], lambda items: None)

    fake.on_assign(fake, [TopicPartition("in", 2)])

    assert fake.pause_calls == 0
    assert fake.assigned == [TopicPartition("in", 0)]  # 交給 client 自動 assign


def test_transient_error_retry_after_overrides_backoff():
    handler, _ = fail_times(1, TransientError("quota", retry_after_s=2.5))
    consumer, fake, _ = build([[msg(1)]], handler, backoff=lambda: itertools.repeat(30))

    consumer.run()

    assert sum(fake.polls) == 2.5


def test_stop_during_retry_wait_returns_promptly_and_resumes():
    calls = []

    def handler(items):
        calls.append(items)
        raise TransientError("down")

    consumer, fake, _ = build([[msg(1)]], handler, backoff=lambda: itertools.repeat(600))
    original_poll = fake.poll

    def poll_then_stop(timeout=-1):
        consumer.stop()
        return original_poll(timeout)

    fake.poll = poll_then_stop

    consumer.run()

    assert len(calls) == 1
    assert len(fake.polls) == 1
    assert fake.commits == 0
    assert fake.paused == set()


def test_commit_assignment_lost_logs_warning_and_keeps_running():
    handled = []
    consumer, fake, _ = build([[msg(1)], [msg(2)]], handled.append)
    fake.commit_errors = [lost(KafkaError._ASSIGNMENT_LOST)]

    consumer.run()

    assert handled == [[Event(id=1)], [Event(id=2)]]
    assert fake.commits == 1


def test_commit_unknown_member_logs_warning_and_keeps_running():
    handled = []
    consumer, fake, _ = build([[msg(1)], [msg(2)]], handled.append)
    fake.commit_errors = [lost(KafkaError.UNKNOWN_MEMBER_ID)]

    consumer.run()

    assert len(handled) == 2
    assert fake.commits == 1


def test_commit_other_kafka_error_raises():
    consumer, fake, _ = build([[msg(1)]], lambda items: None)
    fake.commit_errors = [lost(KafkaError._TRANSPORT)]

    with pytest.raises(KafkaException):
        consumer.run()
    assert fake.closed


# ---------- handler 回報 Rejection（開發規格 7.13） ----------
def dlq_offsets(dlq_producer):
    return [json.loads(m["value"])["offset"] for m in dlq_producer.produced]


def test_rejected_items_go_to_dlq_then_batch_is_committed():
    def handler(items):
        return [Rejection(1, ValueError("bad row"))]

    consumer, fake, dlq_producer = build([[msg(1, 10), msg(2, 11), msg(3, 12)]], handler)

    consumer.run()

    assert dlq_offsets(dlq_producer) == [11]
    assert "ValueError: bad row" in json.loads(dlq_producer.produced[0]["value"])["error"]
    assert fake.commits == 1


def test_rejection_index_maps_to_message_after_undecodable_ones_are_dropped():
    handled = []

    def handler(items):
        handled.append(items)
        return [Rejection(1, ValueError("bad row"))]

    batch = [msg(1, 10), FakeMessage(b"not json", offset_=11), msg(3, 12)]
    consumer, _, dlq_producer = build([batch], handler)

    consumer.run()

    assert handled == [[Event(id=1), Event(id=3)]]
    assert dlq_offsets(dlq_producer) == [11, 12]


def test_handler_returning_none_commits_without_dlq():
    consumer, fake, dlq_producer = build([[msg(1)]], lambda items: None)

    consumer.run()

    assert dlq_producer.produced == []
    assert fake.commits == 1


def test_rejection_index_out_of_range_raises_without_commit():
    consumer, fake, dlq_producer = build([[msg(1)]], lambda items: [Rejection(5, ValueError())])

    with pytest.raises(IndexError):
        consumer.run()

    assert dlq_producer.produced == []
    assert fake.commits == 0


def test_rejections_from_successful_retry_go_to_dlq():
    calls = []

    def handler(items):
        calls.append(items)
        if len(calls) == 1:
            raise TransientError("db down")
        return [Rejection(0, ValueError("bad row"))]

    consumer, fake, dlq_producer = build([[msg(1, 7)]], handler)

    consumer.run()

    assert len(calls) == 2
    assert dlq_offsets(dlq_producer) == [7]
    assert fake.commits == 1

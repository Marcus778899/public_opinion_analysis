import itertools
import json

import pytest
from confluent_kafka import KafkaError, KafkaException
from pydantic import BaseModel

from radar.common.kafka.consumer import BatchConsumer, DecodeError, TransientError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings
from tests.unit.common.kafka.fakes import (
    PARTITION_EOF,
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


def build(batches, handler, dlq_producer=None, decode=None):
    fake = FakeConsumer(batches=batches)
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
        backoff=lambda: itertools.repeat(0),
        decode=decode,
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

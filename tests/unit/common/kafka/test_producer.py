import json

import pytest
from pydantic import BaseModel

from radar.common.kafka.producer import DeliveryError, JsonProducer
from radar.common.settings import KafkaSettings
from tests.unit.common.kafka.fakes import FakeProducer

SETTINGS = KafkaSettings(bootstrap_servers="unused:9092")


class Event(BaseModel):
    id: int
    text: str


def make(fake: FakeProducer) -> JsonProducer:
    return JsonProducer(SETTINGS, producer=fake)


def test_send_serializes_model_as_json_with_utf8_key():
    fake = FakeProducer()

    make(fake).send("t", "Gossiping.M.1", Event(id=1, text="台積電"))

    sent = fake.produced[0]
    assert sent["topic"] == "t"
    assert sent["key"] == b"Gossiping.M.1"
    assert json.loads(sent["value"]) == {"id": 1, "text": "台積電"}


def test_send_retries_once_when_local_queue_full():
    fake = FakeProducer(buffer_full_times=1)

    make(fake).send("t", "k", Event(id=1, text="x"))

    assert len(fake.produced) == 1


def test_flush_succeeds_when_all_delivered():
    producer = make(FakeProducer())
    producer.send("t", "k", Event(id=1, text="x"))

    producer.flush()


def test_flush_raises_when_delivery_failed():
    producer = make(FakeProducer(fail_delivery=True))
    producer.send("t", "k", Event(id=1, text="x"))

    with pytest.raises(DeliveryError):
        producer.flush()


def test_flush_clears_errors_after_raising():
    fake = FakeProducer(fail_delivery=True)
    producer = make(fake)
    producer.send("t", "k", Event(id=1, text="x"))
    with pytest.raises(DeliveryError):
        producer.flush()

    fake.fail_delivery = False
    producer.flush()


def test_flush_raises_timeout_when_messages_remain():
    producer = make(FakeProducer(remaining_on_flush=2))

    with pytest.raises(TimeoutError):
        producer.flush()

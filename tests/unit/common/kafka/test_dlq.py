import base64
import json

from radar.common.kafka.dlq import DLQ_TOPIC, DlqPublisher, to_dlq_record
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings
from tests.unit.common.kafka.fakes import FakeMessage, FakeProducer


def test_to_dlq_record_base64_encodes_payload():
    msg = FakeMessage(b"\xff not json")

    record = to_dlq_record(msg, "ingest", ValueError("bad"))

    assert base64.b64decode(record.payload_b64) == b"\xff not json"


def test_to_dlq_record_keeps_source_position_and_error():
    msg = FakeMessage(b"x", topic_="raw.posts", partition_=2, offset_=42)

    record = to_dlq_record(msg, "ingest", ValueError("bad"))

    assert (record.source_topic, record.partition, record.offset) == ("raw.posts", 2, 42)
    assert record.consumer == "ingest"
    assert record.error == "ValueError: bad"


def test_to_dlq_record_handles_empty_value():
    assert to_dlq_record(FakeMessage(None), "c", ValueError()).payload_b64 == ""


def test_publish_writes_to_dlq_topic_and_flushes():
    fake = FakeProducer()
    publisher = DlqPublisher(JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake), "c")

    publisher.publish(FakeMessage(b"x", key_=b"post-1"), ValueError("bad"))

    assert fake.produced[0]["topic"] == DLQ_TOPIC
    assert fake.produced[0]["key"] == b"post-1"
    assert json.loads(fake.produced[0]["value"])["consumer"] == "c"
    assert fake._pending == []


def test_publish_without_key_uses_source_position():
    fake = FakeProducer()
    publisher = DlqPublisher(JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake), "c")

    keyless = FakeMessage(b"x", key_=None, topic_="in", partition_=1, offset_=7)

    publisher.publish(keyless, ValueError())

    assert fake.produced[0]["key"] == b"in-1-7"

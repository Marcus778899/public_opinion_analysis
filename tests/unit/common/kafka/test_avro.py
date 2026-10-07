import pytest
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext

from radar.common.kafka.avro import make_avro_decoder
from radar.common.kafka.consumer import DecodeError
from radar.common.schemas import CdcPost
from tests.unit.common.kafka.fakes import FakeMessage

TOPIC = "cdc.public.posts"
# 與 Debezium ExtractNewRecordState 產生的欄位一致（S2-01 實測），多的欄位應被忽略
SCHEMA = """{"type": "record", "name": "Value", "fields": [
  {"name": "post_id", "type": "string"}, {"name": "board", "type": "string"},
  {"name": "title", "type": ["null", "string"]}, {"name": "content", "type": ["null", "string"]},
  {"name": "push_count", "type": "int"}, {"name": "is_deleted", "type": "boolean"},
  {"name": "__deleted", "type": ["null", "string"]}, {"name": "__op", "type": ["null", "string"]},
  {"name": "__source_lsn", "type": ["null", "long"]}]}"""


@pytest.fixture
def registry():
    return SchemaRegistryClient.new_client({"url": "mock://avro-test"})


def encode(registry, record: dict) -> bytes:
    serializer = AvroSerializer(registry, SCHEMA)
    return serializer(record, SerializationContext(TOPIC, MessageField.VALUE))


def test_decode_cdc_post_with_aliases(registry):
    value = encode(
        registry,
        {
            "post_id": "Stock.M.1759730000.A.1B2", "board": "Stock", "title": "台積電",
            "content": "內文", "push_count": 3, "is_deleted": False,
            "__deleted": "false", "__op": "c", "__source_lsn": 123,
        },
    )  # fmt: skip

    post = make_avro_decoder(CdcPost, registry)(FakeMessage(value, topic_=TOPIC))

    assert (post.post_id, post.title, post.op, post.source_lsn) == (
        "Stock.M.1759730000.A.1B2",
        "台積電",
        "c",
        123,
    )


def test_decode_garbage_raises_decode_error(registry):
    with pytest.raises(DecodeError):
        make_avro_decoder(CdcPost, registry)(FakeMessage(b"not avro", topic_=TOPIC))


def test_decode_empty_value_raises_decode_error(registry):
    with pytest.raises(DecodeError):
        make_avro_decoder(CdcPost, registry)(FakeMessage(None, topic_=TOPIC))

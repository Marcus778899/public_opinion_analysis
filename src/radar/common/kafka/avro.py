"""解 CDC topic 的 Avro 訊息（Apicurio 以 Confluent 格式序列化，設計文件 6.2）。"""

from collections.abc import Callable

from confluent_kafka import Message
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext, SerializationError
from pydantic import BaseModel

from radar.common.kafka.consumer import DecodeError


def make_avro_decoder[T: BaseModel](
    model: type[T], registry: SchemaRegistryClient
) -> Callable[[Message], T]:
    """壞資料拋 DecodeError（送 DLQ）；schema registry 連不上的錯誤不攔，讓服務停下等重啟。"""
    deserializer = AvroDeserializer(registry)

    def decode(msg: Message) -> T:
        ctx = SerializationContext(msg.topic(), MessageField.VALUE)
        try:
            record = deserializer(msg.value(), ctx)
        except SerializationError as e:
            raise DecodeError(f"avro decode failed: {e}") from e
        if record is None:
            raise DecodeError("tombstone or empty message")
        return model.model_validate(record)

    return decode

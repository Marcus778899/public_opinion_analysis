from confluent_kafka import KafkaError, KafkaException, Message, Producer
from pydantic import BaseModel

from radar.common.kafka.config import producer_config
from radar.common.log import log
from radar.common.settings import KafkaSettings


class DeliveryError(Exception):
    def __init__(self, errors: list[KafkaError]) -> None:
        super().__init__(f"{len(errors)} message(s) failed to deliver: {errors[0]}")
        self.errors = errors


class JsonProducer:
    """把 pydantic model 序列化成 JSON 寫入 Kafka；key 為 UTF-8 字串。"""

    def __init__(self, settings: KafkaSettings, *, producer: Producer | None = None) -> None:
        # NOTE: producer 可注入，單元測試用 fake 取代真的 confluent Producer
        self._producer = producer or Producer(producer_config(settings))
        self._errors: list[KafkaError] = []
        self._partition_counts: dict[str, int] = {}

    def send(self, topic: str, key: str, value: BaseModel, partition: int | None = None) -> None:
        """partition 為 None 時由 key hash 決定。"""
        payload = value.model_dump_json().encode()
        try:
            self._produce(topic, key, payload, partition)
        except BufferError:
            # 本地佇列滿了：先讓已送出的訊息完成 delivery 再重試一次
            self._producer.poll(1.0)
            self._produce(topic, key, payload, partition)
        self._producer.poll(0)

    def partition_count(self, topic: str, timeout_s: float = 5.0) -> int:
        """向 broker 查 topic 的 partition 數；結果快取，避免每次送出都查 metadata。"""
        if topic not in self._partition_counts:
            meta = self._producer.list_topics(topic, timeout=timeout_s).topics.get(topic)
            if meta is None or meta.error is not None or not meta.partitions:
                error = meta.error if meta is not None and meta.error is not None else None
                raise KafkaException(error or KafkaError(KafkaError.UNKNOWN_TOPIC_OR_PART))
            self._partition_counts[topic] = len(meta.partitions)
        return self._partition_counts[topic]

    def flush(self, timeout_s: float = 10.0) -> None:
        remaining = self._producer.flush(timeout_s)
        if remaining:
            raise TimeoutError(f"{remaining} message(s) not delivered within {timeout_s}s")
        if self._errors:
            errors, self._errors = self._errors, []
            raise DeliveryError(errors)

    def _produce(self, topic: str, key: str, payload: bytes, partition: int | None) -> None:
        # NOTE: 不指定時不能傳 None，confluent 只接受 int；省略參數才會用 key hash
        extra = {} if partition is None else {"partition": partition}
        self._producer.produce(
            topic, key=key.encode(), value=payload, on_delivery=self._on_delivery, **extra
        )

    def _on_delivery(self, err: KafkaError | None, msg: Message) -> None:
        if err is not None:
            log.error("delivery failed topic=%s key=%s: %s", msg.topic(), msg.key(), err)
            self._errors.append(err)

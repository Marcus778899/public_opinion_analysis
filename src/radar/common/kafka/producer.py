from confluent_kafka import KafkaError, Message, Producer
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

    def send(self, topic: str, key: str, value: BaseModel) -> None:
        payload = value.model_dump_json().encode()
        try:
            self._produce(topic, key, payload)
        except BufferError:
            # 本地佇列滿了：先讓已送出的訊息完成 delivery 再重試一次
            self._producer.poll(1.0)
            self._produce(topic, key, payload)
        self._producer.poll(0)

    def flush(self, timeout_s: float = 10.0) -> None:
        remaining = self._producer.flush(timeout_s)
        if remaining:
            raise TimeoutError(f"{remaining} message(s) not delivered within {timeout_s}s")
        if self._errors:
            errors, self._errors = self._errors, []
            raise DeliveryError(errors)

    def _produce(self, topic: str, key: str, payload: bytes) -> None:
        self._producer.produce(
            topic, key=key.encode(), value=payload, on_delivery=self._on_delivery
        )

    def _on_delivery(self, err: KafkaError | None, msg: Message) -> None:
        if err is not None:
            log.error("delivery failed topic=%s key=%s: %s", msg.topic(), msg.key(), err)
            self._errors.append(err)

import base64
from datetime import UTC, datetime

from confluent_kafka import Message

from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log
from radar.common.schemas import DlqRecord

DLQ_TOPIC = names.DLQ


def to_dlq_record(msg: Message, consumer: str, error: Exception) -> DlqRecord:
    return DlqRecord(
        source_topic=msg.topic() or "",
        partition=msg.partition() or 0,
        offset=msg.offset() or 0,
        consumer=consumer,
        error=f"{type(error).__name__}: {error}",
        payload_b64=base64.b64encode(msg.value() or b"").decode(),
        failed_at=datetime.now(UTC),
    )


class DlqPublisher:
    def __init__(self, producer: JsonProducer, consumer: str) -> None:
        self._producer = producer
        self._consumer = consumer

    def publish(self, msg: Message, error: Exception) -> None:
        record = to_dlq_record(msg, self._consumer, error)
        raw_key = msg.key()
        if raw_key:
            key = raw_key.decode(errors="replace")
        else:
            key = f"{record.source_topic}-{record.partition}-{record.offset}"
        self._producer.send(DLQ_TOPIC, key, record)
        # 確保 DLQ 已落地，呼叫端才能 commit 原訊息
        self._producer.flush()
        log.warning(
            "sent to dlq topic=%s partition=%s offset=%s: %s",
            record.source_topic,
            record.partition,
            record.offset,
            record.error,
        )

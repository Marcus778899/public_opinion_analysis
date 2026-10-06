"""Kafka 訊息格式（開發規格第 3 章）。ORM model 在 radar.common.db.models，兩者不混用。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class KafkaMessage(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: int = 1


class DlqRecord(BaseModel):
    """開發規格 2.3；不繼承 KafkaMessage，因為它包裝的是任意來源的原始訊息。"""

    source_topic: str
    partition: int
    offset: int
    consumer: str
    error: str
    payload_b64: str
    failed_at: datetime


# TODO(S1-04): CrawlTask、RawPost、RawHtml 等業務訊息在階段 1 加入

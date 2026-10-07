"""[常駐] 串流抽樣標註（S3-08）：消費 cdc.public.posts 的新文章，抽 5% 送 LLM 標註。

用途是監控模型、累積新資料、階段 7 的 shadow 比較，不是線上預測（設計文件 7.5）。
"""

import zlib
from collections.abc import Callable
from datetime import UTC, datetime

from confluent_kafka.schema_registry import SchemaRegistryClient

from radar.common.kafka import names
from radar.common.kafka.avro import make_avro_decoder
from radar.common.kafka.consumer import BatchConsumer, TransientError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.schemas import CdcPost, Label
from radar.common.settings import LabelingSettings, SchemaRegistrySettings, get_kafka_settings
from radar.ml.labeling.factory import build_labeler
from radar.ml.labeling.llm import FallbackLabeler, LabelerError, RetryableLabelerError
from radar.ml.labeling.prompt import PROMPT_VERSION, PostText

SAMPLE_PERCENT = 5
GROUP_ID = "label-stream"
CREATE = "c"


def should_sample(post_id: str, percent: int = SAMPLE_PERCENT) -> bool:
    """同一篇文章每次判斷結果都相同，重跑或重複訊息不會改變抽樣。"""
    # NOTE: 不用內建 hash()，它每個 process 的 seed 不同，重啟後結果會變
    return zlib.crc32(post_id.encode()) % 100 < percent


def is_new_post(op: str | None) -> bool:
    """只處理新文章；snapshot（r）與更新（u）不標註。"""
    return op == CREATE


class StreamLabeler:
    def __init__(
        self,
        labeler: FallbackLabeler,
        publish: Callable[[Label], None],
        flush: Callable[[], None],
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        percent: int = SAMPLE_PERCENT,
    ) -> None:
        self._labeler = labeler
        self._publish = publish
        self._flush = flush
        self._now = now
        self._percent = percent

    def __call__(self, events: list[CdcPost]) -> None:
        """可重試的錯誤拋 TransientError，整批重試；重複標註無妨，下游取最新一筆。"""
        for event in events:
            if event.is_deleted or not is_new_post(event.op):
                continue
            if not should_sample(event.post_id, self._percent):
                continue
            post = PostText(event.post_id, event.board, event.title, event.content)
            try:
                labeler_name, sentiments = self._labeler.label_named(post)
            except RetryableLabelerError as e:
                raise TransientError(str(e)) from e
            except LabelerError as e:
                log.warning("skip %s: %s", event.post_id, e)
                continue
            self._publish(
                Label(
                    post_id=event.post_id,
                    labeler=labeler_name,
                    version=PROMPT_VERSION,
                    labeled_at=self._now(),
                    sentiments=sentiments,
                )
            )
        self._flush()


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("label-stream")
    settings = LabelingSettings()
    providers = [settings.primary, *[p for p in settings.fallbacks if p != settings.primary]]
    labeler = FallbackLabeler([build_labeler(p, settings.max_chars) for p in providers])
    producer = JsonProducer(get_kafka_settings())
    registry = SchemaRegistryClient.new_client({"url": SchemaRegistrySettings().url})
    handler = StreamLabeler(
        labeler,
        publish=lambda label: producer.send(names.LABELS, label.post_id, label),
        flush=producer.flush,
    )
    consumer = BatchConsumer(
        get_kafka_settings(),
        group_id=GROUP_ID,
        topics=[names.CDC_POSTS],
        model=CdcPost,
        handler=handler,
        dlq=DlqPublisher(producer, GROUP_ID),
        batch_size=50,
        decode=make_avro_decoder(CdcPost, registry),
    )
    log.info("labeling %d%% of new posts with %s", SAMPLE_PERCENT, providers)
    try:
        consumer.run()
    finally:
        producer.flush()
        labeler.close()


if __name__ == "__main__":
    main()

"""API 對 Kafka 的操作：手動派發爬取任務、查 DLQ 數量。"""

from confluent_kafka import Consumer, TopicPartition

from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import CrawlTask
from radar.common.tasks import make_list_task, resolve_list_partition


def make_manual_list_task(board: str) -> CrawlTask:
    return make_list_task(board, CrawlReason.MANUAL)


def dispatch_task(
    producer: JsonProducer, task: CrawlTask, enabled_boards: list[str] | None = None
) -> None:
    """寫入 crawl.tasks 並 flush，讓 API 回應時任務已落地。

    列表任務依 enabled_boards 指定 partition（開發規格 7.10）。
    """
    partition = None
    if task.type is CrawlTaskType.LIST and enabled_boards is not None:
        partition = resolve_list_partition(
            task.board, enabled_boards, lambda: producer.partition_count(names.CRAWL_TASKS)
        )
    producer.send(names.CRAWL_TASKS, task.kafka_key(), task, partition=partition)
    producer.flush()


def count_dlq_messages(consumer: Consumer, timeout_s: float = 5.0) -> int:
    """各 partition 的 high - low watermark 加總；DLQ 保留 30 天，即近 30 天的數量。"""
    metadata = consumer.list_topics(names.DLQ, timeout=timeout_s)
    topic = metadata.topics.get(names.DLQ)
    if topic is None or topic.error is not None:
        return 0
    total = 0
    for partition in topic.partitions:
        low, high = consumer.get_watermark_offsets(
            TopicPartition(names.DLQ, partition), timeout=timeout_s, cached=False
        )
        total += high - low
    return total

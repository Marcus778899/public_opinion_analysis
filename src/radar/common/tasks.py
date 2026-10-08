"""建立 crawl.tasks 的任務；API（手動觸發）與 Scheduler（定時、重爬）共用。"""

import uuid
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from confluent_kafka import KafkaException

from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.ids import board_index_url
from radar.common.log import log
from radar.common.schemas import CrawlTask


def make_list_task(board: str, reason: CrawlReason, now: datetime | None = None) -> CrawlTask:
    return CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.LIST,
        board=board,
        url=board_index_url(board),
        reason=reason,
        created_at=now or datetime.now(UTC),
    )


def list_task_partition(
    board: str, enabled_boards: Iterable[str], num_partitions: int
) -> int | None:
    """列表任務要送往的 partition（開發規格 7.10）；None 代表退回 key hash。"""
    names = sorted(set(enabled_boards))
    if num_partitions < 1 or board not in names:
        return None
    return names.index(board) % num_partitions


def resolve_list_partition(
    board: str, enabled_boards: Iterable[str], partition_count: Callable[[], int]
) -> int | None:
    """同 list_task_partition，但查不到 partition 數時退回 key hash，不讓任務停送。"""
    try:
        count = partition_count()
    except KafkaException as e:
        log.warning("partition count unavailable, fallback to key hash: %s", e)
        return None
    return list_task_partition(board, enabled_boards, count)


def make_post_task(
    post_id: str, board: str, url: str, reason: CrawlReason, now: datetime | None = None
) -> CrawlTask:
    return CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.POST,
        board=board,
        url=url,
        post_id=post_id,
        reason=reason,
        created_at=now or datetime.now(UTC),
    )

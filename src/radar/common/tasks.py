"""建立 crawl.tasks 的任務；API（手動觸發）與 Scheduler（定時、重爬）共用。"""

import uuid
from datetime import UTC, datetime

from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.ids import board_index_url
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

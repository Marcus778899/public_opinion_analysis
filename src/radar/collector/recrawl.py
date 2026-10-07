"""近期文章重爬（設計文件 4.2、4.5）：依文章年齡決定下次重爬時間，寫入 crawl_state。"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from radar.common.db.models import Board, CrawlState, Post
from radar.common.enums import CrawlReason
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log
from radar.common.tasks import make_post_task

# (文章年齡上限, 重爬間隔)；超過最後一級就停止重爬
RECRAWL_TIERS: tuple[tuple[timedelta, timedelta], ...] = (
    (timedelta(hours=1), timedelta(minutes=2)),
    (timedelta(hours=6), timedelta(minutes=10)),
    (timedelta(hours=24), timedelta(hours=1)),
)
# 文章滿這個年齡後才套用 recrawl_min_push 門檻
THRESHOLD_AFTER = timedelta(hours=1)
MAX_AGE = RECRAWL_TIERS[-1][0]
# 停止重爬的文章把下次時間設到很久以後；查詢本身也會排除超過 24 小時的文章
NEVER = timedelta(days=365)


@dataclass(frozen=True)
class DuePost:
    post_id: str
    board: str
    url: str
    created_at: datetime


def next_crawl_at(
    created_at: datetime, now: datetime, *, time_scale: float = 1.0
) -> datetime | None:
    """依文章年齡回傳下次重爬時間；超過 24 小時回傳 None（停止重爬）。"""
    age = now - created_at
    for max_age, interval in RECRAWL_TIERS:
        if age < max_age:
            return now + interval * time_scale
    return None


def find_due_posts(session: Session, now: datetime, *, limit: int) -> list[DuePost]:
    """設計文件 4.5 的查詢：24 小時內、未刪除、達門檻、看板啟用中、且已到期的文章。

    從沒派發過的排最前面，其餘依到期時間排序；超過 limit 的留到下一輪。
    """
    stmt = (
        select(Post.post_id, Post.board, Post.url, Post.created_at)
        .join(Board, Board.board == Post.board)
        .outerjoin(CrawlState, CrawlState.post_id == Post.post_id)
        .where(
            Board.enabled.is_(True),
            Post.is_deleted.is_(False),
            Post.created_at > now - MAX_AGE,
            or_(
                Post.created_at > now - THRESHOLD_AFTER,
                Post.push_count >= Board.recrawl_min_push,
            ),
            or_(CrawlState.next_crawl_at.is_(None), CrawlState.next_crawl_at <= now),
        )
        .order_by(CrawlState.next_crawl_at.asc().nulls_first(), Post.created_at.desc())
        .limit(limit)
    )
    return [DuePost(*row) for row in session.execute(stmt)]


def record_dispatch(
    session: Session, posts: list[DuePost], now: datetime, *, time_scale: float
) -> None:
    """upsert crawl_state；呼叫端負責 commit。"""
    if not posts:
        return
    rows = [
        {
            "post_id": p.post_id,
            "next_crawl_at": next_crawl_at(p.created_at, now, time_scale=time_scale) or now + NEVER,
            "last_dispatched": now,
        }
        for p in posts
    ]
    stmt = insert(CrawlState).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[CrawlState.post_id],
        set_={
            "next_crawl_at": stmt.excluded.next_crawl_at,
            "last_dispatched": stmt.excluded.last_dispatched,
        },
    )
    session.execute(stmt)


class DuePostDispatcher:
    """每輪：查到期文章 → 送 post 任務並 flush → 寫 crawl_state → commit。

    先送 Kafka 再寫 DB：送出失敗就不推進排程，下一輪重試；寫 DB 失敗只會重複派發，無害。
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        producer: JsonProducer,
        *,
        limit: int,
        time_scale: float,
    ) -> None:
        self._session_factory = session_factory
        self._producer = producer
        self._limit = limit
        self._time_scale = time_scale

    def __call__(self, now: datetime | None = None) -> int:
        """回傳派發數量。"""
        now = now or datetime.now(UTC)
        with self._session_factory() as session:
            due = find_due_posts(session, now, limit=self._limit)
            if not due:
                return 0
            for post in due:
                task = make_post_task(post.post_id, post.board, post.url, CrawlReason.RECRAWL, now)
                self._producer.send(names.CRAWL_TASKS, task.kafka_key(), task)
            self._producer.flush()
            record_dispatch(session, due, now, time_scale=self._time_scale)
            session.commit()
        log.info("dispatched %d recrawl tasks", len(due))
        return len(due)

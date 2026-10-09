"""raw.posts → posts / comments（設計文件 5.1、5.2；開發規格 7.3）。

同一個 transaction 寫入；帶條件的 upsert 讓「舊快照不覆蓋新的、沒變化就不寫」，
沒寫入就不產生 CDC 事件。
"""

from dataclasses import dataclass

from sqlalchemy import DateTime, Integer, String, column, delete, false, or_, select, update, values
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from radar.common.db.models import Comment, Post
from radar.common.kafka.consumer import Rejection
from radar.common.schemas import RawPost

# 這筆資料本身有問題：逐筆寫入、送 DLQ（開發規格 7.13）；其他 DB 錯誤仍中止服務
DATA_ERRORS = (IntegrityError, DataError)

# NOTE: PG 單一語句參數上限 65535；comments 6 欄，每批 5000 列約 30000 個參數
COMMENT_CHUNK_SIZE = 5000

# 這些欄位變了才算「有變化」；crawled_at 不列入，否則每次重爬都會產生 CDC 事件
_CHANGE_COLUMNS = ("push_count", "boo_count", "title", "content")
_COMMENT_COLUMNS = ("type", "user_id", "content", "commented_at")


@dataclass(frozen=True)
class WriteStats:
    received: int
    posts_written: int
    comments_written: int
    comments_deleted: int
    marked_deleted: int


def dedupe_posts(posts: list[RawPost]) -> list[RawPost]:
    """同批同 post_id 只留 crawled_at 最新的一筆（ON CONFLICT 不能更新同一列兩次）。"""
    latest: dict[str, RawPost] = {}
    for post in posts:
        current = latest.get(post.post_id)
        if current is None or post.crawled_at > current.crawled_at:
            latest[post.post_id] = post
    return list(latest.values())


def write_batch(session: Session, posts: list[RawPost]) -> WriteStats:
    """呼叫端負責 commit；失敗時整批 rollback。"""
    unique = dedupe_posts(posts)
    live = [p for p in unique if not p.is_deleted]
    deleted = [p for p in unique if p.is_deleted]
    posts_written = upsert_posts(session, live)
    comments_written, comments_deleted = sync_comments(session, live)
    return WriteStats(
        received=len(posts),
        posts_written=posts_written,
        comments_written=comments_written,
        comments_deleted=comments_deleted,
        marked_deleted=mark_deleted(session, deleted),
    )


def write_each(session: Session, posts: list[RawPost]) -> tuple[WriteStats, list[Rejection]]:
    """逐筆模式（開發規格 7.13）：同批去重後每筆一個 savepoint，資料錯誤的回報 index。

    呼叫端負責 commit；OperationalError 照常往外拋（整批重試）。
    """
    latest: dict[str, int] = {}
    for i, post in enumerate(posts):
        j = latest.get(post.post_id)
        if j is None or post.crawled_at > posts[j].crawled_at:
            latest[post.post_id] = i
    written = comments = comments_deleted = deleted = 0
    rejections: list[Rejection] = []
    for i in latest.values():
        try:
            with session.begin_nested():
                stats = write_batch(session, [posts[i]])
        except DATA_ERRORS as e:
            rejections.append(Rejection(i, e))
            continue
        written += stats.posts_written
        comments += stats.comments_written
        comments_deleted += stats.comments_deleted
        deleted += stats.marked_deleted
    return WriteStats(len(posts), written, comments, comments_deleted, deleted), rejections


def upsert_posts(session: Session, posts: list[RawPost]) -> int:
    """回傳實際寫入（新增或更新）的列數。

    已標記刪除的文章收到較新的快照算有變化，is_deleted 改回 false（開發規格 7.14）。
    """
    if not posts:
        return 0
    stmt = insert(Post).values(
        [
            {
                "post_id": p.post_id,
                "board": p.board,
                "author": p.author,
                "title": p.title,
                "content": p.content,
                "url": p.url,
                "push_count": p.push_count,
                "boo_count": p.boo_count,
                "created_at": p.created_at,
                "crawled_at": p.crawled_at,
            }
            for p in posts
        ]
    )
    new = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        index_elements=[Post.post_id],
        set_={**{col: new[col] for col in (*_CHANGE_COLUMNS, "crawled_at")}, "is_deleted": false()},
        where=(Post.crawled_at < new.crawled_at)
        & or_(
            Post.is_deleted,
            *(getattr(Post, col).is_distinct_from(new[col]) for col in _CHANGE_COLUMNS),
        ),
    ).returning(Post.post_id)
    return len(session.execute(stmt).all())


def sync_comments(session: Session, posts: list[RawPost]) -> tuple[int, int]:
    """推文同步（開發規格 7.15）；須在 upsert_posts 之後呼叫。回傳 (新增或更新, 刪除) 列數。"""
    targets = comment_sync_targets(session, posts)
    return upsert_comments(session, targets), delete_trailing_comments(session, targets)


def comment_sync_targets(session: Session, posts: list[RawPost]) -> list[RawPost]:
    """posts.crawled_at 不比快照新的文章；較舊的快照不碰推文，避免刪掉較新的推文。"""
    if not posts:
        return []
    snapshots = values(
        column("post_id", String), column("crawled_at", DateTime(timezone=True)), name="snapshots"
    ).data([(p.post_id, p.crawled_at) for p in posts])
    stmt = select(Post.post_id).where(
        Post.post_id == snapshots.c.post_id, Post.crawled_at <= snapshots.c.crawled_at
    )
    eligible = set(session.scalars(stmt))
    return [p for p in posts if p.post_id in eligible]


def upsert_comments(session: Session, posts: list[RawPost]) -> int:
    """同一樓層內容不同才更新；回傳新增或更新的列數。"""
    rows = [
        {
            "post_id": p.post_id,
            "floor": c.floor,
            "type": c.type,
            "user_id": c.user_id,
            "content": c.content,
            "commented_at": c.commented_at,
        }
        for p in posts
        for c in p.comments
    ]
    written = 0
    for start in range(0, len(rows), COMMENT_CHUNK_SIZE):
        stmt = insert(Comment).values(rows[start : start + COMMENT_CHUNK_SIZE])
        new = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[Comment.post_id, Comment.floor],
            set_={col: new[col] for col in _COMMENT_COLUMNS},
            where=or_(
                *(getattr(Comment, col).is_distinct_from(new[col]) for col in _COMMENT_COLUMNS)
            ),
        ).returning(Comment.post_id)
        written += len(session.execute(stmt).all())
    return written


def delete_trailing_comments(session: Session, posts: list[RawPost]) -> int:
    """刪掉超過新快照最大樓層的推文（沒推文時全刪）；回傳刪除列數。"""
    if not posts:
        return 0
    snapshots = values(
        column("post_id", String), column("max_floor", Integer), name="snapshots"
    ).data([(p.post_id, max((c.floor for c in p.comments), default=0)) for p in posts])
    stmt = delete(Comment).where(
        Comment.post_id == snapshots.c.post_id, Comment.floor > snapshots.c.max_floor
    )
    return session.execute(stmt).rowcount


def mark_deleted(session: Session, posts: list[RawPost]) -> int:
    """把既有文章標記刪除並更新 crawled_at，其他欄位保留最後一次的內容。

    從未見過的、已標記過的、比 crawled_at 舊的都不寫（開發規格 7.14）。
    """
    if not posts:
        return 0
    snapshots = values(
        column("post_id", String), column("crawled_at", DateTime(timezone=True)), name="snapshots"
    ).data([(p.post_id, p.crawled_at) for p in posts])
    stmt = (
        update(Post)
        .where(
            Post.post_id == snapshots.c.post_id,
            Post.is_deleted.is_(False),
            Post.crawled_at < snapshots.c.crawled_at,
        )
        .values(is_deleted=True, crawled_at=snapshots.c.crawled_at)
    )
    return session.execute(stmt).rowcount

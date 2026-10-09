"""raw.posts → posts / comments（設計文件 5.1、5.2；開發規格 7.3）。

同一個 transaction 寫入；帶條件的 upsert 讓「舊快照不覆蓋新的、沒變化就不寫」，
沒寫入就不產生 CDC 事件。
"""

from dataclasses import dataclass

from sqlalchemy import or_, update
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


@dataclass(frozen=True)
class WriteStats:
    received: int
    posts_written: int
    comments_inserted: int
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
    return WriteStats(
        received=len(posts),
        posts_written=upsert_posts(session, live),
        comments_inserted=insert_comments(session, live),
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
    written = comments = deleted = 0
    rejections: list[Rejection] = []
    for i in latest.values():
        try:
            with session.begin_nested():
                stats = write_batch(session, [posts[i]])
        except DATA_ERRORS as e:
            rejections.append(Rejection(i, e))
            continue
        written += stats.posts_written
        comments += stats.comments_inserted
        deleted += stats.marked_deleted
    return WriteStats(len(posts), written, comments, deleted), rejections


def upsert_posts(session: Session, posts: list[RawPost]) -> int:
    """回傳實際寫入（新增或更新）的列數。"""
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
        set_={col: new[col] for col in (*_CHANGE_COLUMNS, "crawled_at")},
        where=(Post.crawled_at < new.crawled_at)
        & or_(*(getattr(Post, col).is_distinct_from(new[col]) for col in _CHANGE_COLUMNS)),
    ).returning(Post.post_id)
    return len(session.execute(stmt).all())


def insert_comments(session: Session, posts: list[RawPost]) -> int:
    """ON CONFLICT (post_id, floor) DO NOTHING；回傳新增列數。"""
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
    inserted = 0
    for start in range(0, len(rows), COMMENT_CHUNK_SIZE):
        stmt = (
            insert(Comment)
            .values(rows[start : start + COMMENT_CHUNK_SIZE])
            .on_conflict_do_nothing(index_elements=[Comment.post_id, Comment.floor])
            .returning(Comment.post_id)
        )
        inserted += len(session.execute(stmt).all())
    return inserted


def mark_deleted(session: Session, posts: list[RawPost]) -> int:
    """只把既有文章的 is_deleted 設為 true，其他欄位保留最後一次的內容。

    從未見過的文章不新增；已標記過的不重複寫，避免多餘的 CDC 事件。
    """
    if not posts:
        return 0
    stmt = (
        update(Post)
        .where(Post.post_id.in_([p.post_id for p in posts]), Post.is_deleted.is_(False))
        .values(is_deleted=True)
    )
    return session.execute(stmt).rowcount

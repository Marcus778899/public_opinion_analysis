"""PG 表定義，schema 的唯一來源（見 docs/development-spec.md 2.4）。

每張表的 comment 註明寫入者與是否被 Debezium 監聽（設計文件 5.4）。
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from radar.common.enums import CommentType

# NOTE: 固定約束命名規則，Alembic 產生的名稱才穩定、日後能 drop
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {datetime: DateTime(timezone=True)}


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_created_at", "created_at"),
        {"comment": "writer: ingest; debezium: yes"},
    )

    post_id: Mapped[str] = mapped_column(Text, primary_key=True)
    board: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    push_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    boo_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime]
    crawled_at: Mapped[datetime]
    is_deleted: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = ({"comment": "writer: ingest; debezium: yes"},)

    post_id: Mapped[str] = mapped_column(Text, ForeignKey("posts.post_id"), primary_key=True)
    floor: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NOTE: 不用 PG 原生 enum，加值時不必 ALTER TYPE；以 CHECK 約束取代
    type: Mapped[CommentType] = mapped_column(
        Enum(
            CommentType,
            native_enum=False,
            create_constraint=True,
            length=8,
            values_callable=lambda e: [m.value for m in e],
            name="comment_type",
        )
    )
    user_id: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str | None] = mapped_column(Text)
    commented_at: Mapped[datetime | None]


class Board(Base):
    __tablename__ = "boards"
    __table_args__ = (
        CheckConstraint("interval_sec >= 30", name="interval_sec_min"),
        CheckConstraint("recrawl_min_push >= 0", name="recrawl_min_push_nonneg"),
        {"comment": "writer: api; debezium: no"},
    )

    board: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    interval_sec: Mapped[int] = mapped_column(Integer)
    # 開發規格 7.2：文章滿 1 小時後，推文數低於此值就停止重爬
    recrawl_min_push: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class CrawlState(Base):
    __tablename__ = "crawl_state"
    __table_args__ = (
        Index("ix_crawl_state_next_crawl_at", "next_crawl_at"),
        {"comment": "writer: scheduler; debezium: no"},
    )

    post_id: Mapped[str] = mapped_column(Text, ForeignKey("posts.post_id"), primary_key=True)
    next_crawl_at: Mapped[datetime]
    last_dispatched: Mapped[datetime]

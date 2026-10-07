"""Kafka 訊息格式（開發規格第 3 章）。ORM model 在 radar.common.db.models，兩者不混用。"""

from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Self
from uuid import UUID

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from radar.common.enums import CommentType, CrawlReason, CrawlTaskType
from radar.common.ids import split_post_id

# 必須帶時區，並統一轉成 UTC（開發規格 2.1）
UtcDatetime = Annotated[AwareDatetime, AfterValidator(lambda v: v.astimezone(UTC))]


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


class CrawlTask(KafkaMessage):
    """topic: crawl.tasks；key: list 任務用 board，post 任務用 post_id（開發規格 7.1）。"""

    task_id: UUID
    type: CrawlTaskType
    board: str
    url: str
    post_id: str | None = None
    reason: CrawlReason
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _check_post_id(self) -> Self:
        if self.type is CrawlTaskType.LIST:
            if self.post_id is not None:
                raise ValueError("list task must not carry post_id")
        elif self.post_id is None:
            raise ValueError("post task requires post_id")
        else:
            _check_belongs_to_board(self.post_id, self.board)
        return self

    def kafka_key(self) -> str:
        return self.post_id if self.type is CrawlTaskType.POST and self.post_id else self.board


class RawComment(BaseModel):
    model_config = ConfigDict(frozen=True)

    floor: int = Field(ge=1)
    type: CommentType
    user_id: str | None
    content: str | None
    # NOTE: 推文時間沒有年份且可能缺漏，parser 推不出來時為 None
    commented_at: UtcDatetime | None


class RawPost(KafkaMessage):
    """topic: raw.posts；key: post_id。一則訊息是一篇文章與其全部推文的快照。"""

    task_id: UUID
    post_id: str
    board: str
    url: str
    author: str | None
    title: str | None
    content: str | None
    created_at: UtcDatetime
    crawled_at: UtcDatetime
    push_count: int = Field(ge=0)
    boo_count: int = Field(ge=0)
    is_deleted: bool = False
    comments: list[RawComment] = []

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        _check_belongs_to_board(self.post_id, self.board)
        floors = Counter(c.floor for c in self.comments)
        duplicated = sorted(f for f, n in floors.items() if n > 1)
        if duplicated:
            raise ValueError(f"duplicate comment floors: {duplicated}")
        # NOTE: 推噓數由 parser 從推文算出，對不上代表 parser 有 bug，送 DLQ 及早發現
        types = Counter(c.type for c in self.comments)
        if (self.push_count, self.boo_count) != (types[CommentType.PUSH], types[CommentType.BOO]):
            raise ValueError(
                f"counts mismatch comments: push {self.push_count} vs {types[CommentType.PUSH]}, "
                f"boo {self.boo_count} vs {types[CommentType.BOO]}"
            )
        return self


class RawHtml(KafkaMessage):
    """topic: raw.html；key: post_id。保留 3 天供 parser 有 bug 時重新解析。"""

    post_id: str
    url: str
    crawled_at: UtcDatetime
    html: str


def _check_belongs_to_board(post_id: str, board: str) -> None:
    post_board, _ = split_post_id(post_id)
    if post_board != board:
        raise ValueError(f"post_id {post_id!r} does not belong to board {board!r}")

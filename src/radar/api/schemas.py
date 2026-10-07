"""API 的請求 / 回應格式；與 Kafka 訊息（radar.common.schemas）、ORM model 分開。"""

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from radar.common.ids import is_valid_board

INTERVAL_SEC_MIN = 30  # 與 boards 表的 CHECK 約束一致


class BoardCreate(BaseModel):
    board: str
    interval_sec: int = Field(ge=INTERVAL_SEC_MIN)
    enabled: bool = True
    recrawl_min_push: int = Field(default=0, ge=0)

    @field_validator("board")
    @classmethod
    def _check_board(cls, value: str) -> str:
        if not is_valid_board(value):
            raise ValueError("board may only contain letters, digits, '_' and '-'")
        return value


class BoardUpdate(BaseModel):
    """PATCH：只更新有給的欄位；給 null 視為沒給。"""

    interval_sec: int | None = Field(default=None, ge=INTERVAL_SEC_MIN)
    enabled: bool | None = None
    recrawl_min_push: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _check_not_empty(self) -> Self:
        if not self.changes():
            raise ValueError("at least one field must be provided")
        return self

    def changes(self) -> dict[str, Any]:
        return self.model_dump(exclude_unset=True, exclude_none=True)


class BoardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    board: str
    enabled: bool
    interval_sec: int
    recrawl_min_push: int
    updated_at: datetime


class CrawlAccepted(BaseModel):
    task_id: str
    board: str


class BoardStatus(BaseModel):
    board: str
    enabled: bool
    # NOTE: posts 只在內容有變化時寫入，這是「最後一次有變化」的時間，不是最後爬取時間
    last_changed_at: datetime | None
    post_count_24h: int


class StatusOut(BaseModel):
    boards: list[BoardStatus]
    # 查不到 Kafka 時為 -1
    dlq_count: int

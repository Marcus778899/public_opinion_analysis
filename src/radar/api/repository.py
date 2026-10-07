"""boards 表的讀寫與 /status 的統計查詢；FastAPI 是 boards 唯一的寫入者（設計文件 5.4）。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar.api.schemas import BoardCreate, BoardStatus, BoardUpdate
from radar.common.db.models import Board, Post


class BoardExistsError(Exception):
    pass


class BoardNotFoundError(Exception):
    pass


class BoardRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[Board]:
        return list(self._session.scalars(select(Board).order_by(Board.board)))

    def get(self, board: str) -> Board:
        obj = self._session.get(Board, board)
        if obj is None:
            raise BoardNotFoundError(board)
        return obj

    def create(self, data: BoardCreate) -> Board:
        obj = Board(**data.model_dump())
        self._session.add(obj)
        try:
            self._session.commit()
        except IntegrityError as e:
            self._session.rollback()
            raise BoardExistsError(data.board) from e
        self._session.refresh(obj)
        return obj

    def update(self, board: str, data: BoardUpdate) -> Board:
        obj = self.get(board)
        for key, value in data.changes().items():
            setattr(obj, key, value)
        self._session.commit()
        self._session.refresh(obj)
        return obj

    def statuses(self, now: datetime | None = None) -> list[BoardStatus]:
        cutoff = (now or datetime.now(UTC)) - timedelta(hours=24)
        stmt = (
            select(
                Board.board,
                Board.enabled,
                func.max(Post.crawled_at),
                func.count(Post.post_id).filter(Post.created_at >= cutoff),
            )
            # LEFT JOIN：還沒有文章的看板也要列出
            .outerjoin(Post, Post.board == Board.board)
            .group_by(Board.board, Board.enabled)
            .order_by(Board.board)
        )
        return [
            BoardStatus(board=b, enabled=e, last_changed_at=last, post_count_24h=count)
            for b, e, last, count in self._session.execute(stmt)
        ]

"""subscriptions 表的讀寫（bot 是唯一的寫入者，設計文件 5.4）與 boards 的唯讀查詢。"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from radar.common.db.models import Board, Subscription

BOARD = "board"


class SubscriptionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def subscribe(self, chat_id: int, board: str) -> bool:
        """回傳是否為新的訂閱；重複訂閱不報錯。"""
        if self._session.get(Subscription, (chat_id, BOARD, board)) is not None:
            return False
        self._session.add(Subscription(chat_id=chat_id, unit_type=BOARD, unit_key=board))
        self._session.commit()
        return True

    def unsubscribe(self, chat_id: int, board: str | None) -> int:
        """board 為 None 時取消該 chat 的全部訂閱；回傳刪除筆數。"""
        stmt = delete(Subscription).where(Subscription.chat_id == chat_id)
        if board is not None:
            stmt = stmt.where(Subscription.unit_type == BOARD, Subscription.unit_key == board)
        deleted = self._session.execute(stmt).rowcount
        self._session.commit()
        return deleted

    def boards_of(self, chat_id: int) -> list[str]:
        stmt = (
            select(Subscription.unit_key)
            .where(Subscription.chat_id == chat_id, Subscription.unit_type == BOARD)
            .order_by(Subscription.unit_key)
        )
        return list(self._session.scalars(stmt))

    def chats_for_board(self, board: str) -> list[int]:
        stmt = (
            select(Subscription.chat_id)
            .where(Subscription.unit_type == BOARD, Subscription.unit_key == board)
            .order_by(Subscription.chat_id)
        )
        return list(self._session.scalars(stmt))

    def enabled_boards(self) -> list[str]:
        """boards 中啟用的看板，依名稱排序；只讀，寫入者仍是 API。"""
        stmt = select(Board.board).where(Board.enabled.is_(True)).order_by(Board.board)
        return list(self._session.scalars(stmt))

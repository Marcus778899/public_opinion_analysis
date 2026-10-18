"""subscriptions、chat_settings、muted_posts 的讀寫（bot 是唯一的寫入者，設計文件 5.4）。

boards 只讀，寫入者仍是 API。
"""

from datetime import datetime
from typing import Literal

from sqlalchemy import and_, delete, exists, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.bot.views import ChatPrefs
from radar.common.db.models import Board, ChatSettings, MutedPost, Subscription
from radar.common.schemas import Alert

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

    def enabled_boards(self) -> list[str]:
        """boards 中啟用的看板，依名稱排序；只讀，寫入者仍是 API。"""
        stmt = select(Board.board).where(Board.enabled.is_(True)).order_by(Board.board)
        return list(self._session.scalars(stmt))


class PreferenceRepository:
    """通知設定與「不再通知」（開發規格 7.23）。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def prefs(self, chat_id: int) -> ChatPrefs:
        """沒有列時回傳預設（全部開啟），不寫入。"""
        row = self._session.get(ChatSettings, chat_id)
        if row is None:
            return ChatPrefs()
        return ChatPrefs(post_alerts=row.post_alerts, board_alerts=row.board_alerts)

    def toggle(self, chat_id: int, unit_type: Literal["post", "board"]) -> ChatPrefs:
        """切換一種警示的開關，回傳切換後的設定；沒有列時先以預設建立。"""
        row = self._session.get(ChatSettings, chat_id)
        if row is None:
            row = ChatSettings(chat_id=chat_id, post_alerts=True, board_alerts=True)
            self._session.add(row)
        if unit_type == "post":
            row.post_alerts = not row.post_alerts
        else:
            row.board_alerts = not row.board_alerts
        self._session.commit()
        return ChatPrefs(post_alerts=row.post_alerts, board_alerts=row.board_alerts)

    def mute(self, chat_id: int, post_id: str) -> bool:
        """回傳是否為新增；重複不報錯。"""
        stmt = (
            insert(MutedPost)
            .values(chat_id=chat_id, post_id=post_id)
            .on_conflict_do_nothing()
            .returning(MutedPost.post_id)
        )
        added = self._session.execute(stmt).first() is not None
        self._session.commit()
        return added

    def unmute(self, chat_id: int, post_id: str) -> bool:
        stmt = delete(MutedPost).where(MutedPost.chat_id == chat_id, MutedPost.post_id == post_id)
        removed = self._session.execute(stmt).rowcount > 0
        self._session.commit()
        return removed

    def muted(self, chat_id: int) -> list[str]:
        """post_id，最近加入的在前。"""
        stmt = (
            select(MutedPost.post_id)
            .where(MutedPost.chat_id == chat_id)
            .order_by(MutedPost.muted_at.desc(), MutedPost.post_id)
        )
        return list(self._session.scalars(stmt))

    def purge_muted(self, before: datetime) -> int:
        """刪掉 muted_at 早於 before 的列，回傳刪除筆數。"""
        deleted = self._session.execute(delete(MutedPost).where(MutedPost.muted_at < before))
        self._session.commit()
        return deleted.rowcount

    def recipients(self, alert: Alert) -> list[int]:
        """訂閱該看板、沒關掉這種警示、（文章警示）沒把這篇設為不再通知的 chat。"""
        enabled = (
            ChatSettings.post_alerts if alert.unit_type == "post" else ChatSettings.board_alerts
        )
        stmt = (
            select(Subscription.chat_id)
            .outerjoin(ChatSettings, ChatSettings.chat_id == Subscription.chat_id)
            .where(
                Subscription.unit_type == BOARD,
                Subscription.unit_key == alert.board,
                # 沒有 chat_settings 列 = 全部開啟
                or_(ChatSettings.chat_id.is_(None), enabled.is_(True)),
            )
            .order_by(Subscription.chat_id)
        )
        if alert.unit_type == "post":
            muted = exists().where(
                and_(MutedPost.chat_id == Subscription.chat_id, MutedPost.post_id == alert.unit_key)
            )
            stmt = stmt.where(~muted)
        return list(self._session.scalars(stmt))

    def forget(self, chat_id: int) -> None:
        """使用者封鎖 bot（403）：刪掉該 chat 的訂閱、設定與不再通知。"""
        for model in (Subscription, ChatSettings, MutedPost):
            self._session.execute(delete(model).where(model.chat_id == chat_id))
        self._session.commit()

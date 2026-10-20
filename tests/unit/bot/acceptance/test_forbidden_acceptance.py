"""驗收 bot-forbidden-crash（資安 H-1、開發規格 7.21）：指令與按鈕路徑遇到 403。

只走對外入口 poll_commands／handle_update；PG 用記憶體 SQLite，驗證「該 chat 的資料被刪」。
"""

import threading
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from radar.bot.main import handle_update, poll_commands
from radar.bot.telegram import (
    CallbackQuery,
    IncomingMessage,
    TelegramForbiddenError,
    Update,
)
from radar.common.db.models import ChatSettings, MutedPost, Subscription
from radar.common.settings import TelegramSettings

NOW = datetime(2026, 10, 20, 3, 0, tzinfo=UTC)
BLOCKED = 42
OTHER = 7


class FakeQueries:
    def post_stats(self, post_ids):
        return {}

    def hot(self, boards):
        return []

    def overview(self, board, now):
        return None


class ServerTelegram:
    """模擬 Bot API：對 forbidden_chats 一律 403；offset 之前未確認的 update 會重送。"""

    def __init__(self, pending: list[Update], forbidden_chats=(BLOCKED,)):
        self.pending = list(pending)
        self.forbidden = set(forbidden_chats)
        self.stop = threading.Event()
        self.polls = 0
        self.sent: list[int] = []
        self.edited: list[int] = []
        self.answered: list[str] = []

    def get_updates(self, offset, timeout_s):
        self.polls += 1
        if offset is not None:
            self.pending = [u for u in self.pending if u.update_id >= offset]
        if self.polls > 3:
            self.stop.set()
            return []
        return list(self.pending)

    def _check(self, chat_id):
        if chat_id in self.forbidden:
            raise TelegramForbiddenError(chat_id)

    def send_message(self, chat_id, text, keyboard=None):
        self._check(chat_id)
        self.sent.append(chat_id)

    def edit_message_text(self, chat_id, message_id, text, keyboard=None):
        self._check(chat_id)
        self.edited.append(chat_id)

    def answer_callback_query(self, callback_id, text=None):
        self.answered.append(callback_id)


@pytest.fixture
def sessions():
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    for model in (Subscription, ChatSettings, MutedPost):
        model.__table__.create(engine)
    factory = sessionmaker(engine)
    with factory() as s:
        for chat in (BLOCKED, OTHER):
            s.add(Subscription(chat_id=chat, unit_type="board", unit_key="Stock"))
            s.add(ChatSettings(chat_id=chat))
            s.add(MutedPost(chat_id=chat, post_id="Stock.M.1.A.AAA"))
        s.commit()
    return factory


def settings() -> TelegramSettings:
    return TelegramSettings(bot_token="t", allowed_chat_ids=[], poll_timeout_s=1)


def msg(update_id: int, chat_id: int, text: str = "/start") -> Update:
    return Update(update_id=update_id, message=IncomingMessage(chat_id=chat_id, text=text))


def button(update_id: int, chat_id: int, data: str = "1:menu:") -> Update:
    cb = CallbackQuery(id=f"cb{update_id}", chat_id=chat_id, message_id=9, data=data)
    return Update(update_id=update_id, callback=cb)


def poll(telegram: ServerTelegram, sessions) -> None:
    poll_commands(
        telegram,  # type: ignore[arg-type]
        settings(),
        sessions,
        FakeQueries(),  # type: ignore[arg-type]
        telegram.stop,
        wait=lambda s: False,
        clock=lambda: NOW,
    )


def rows(sessions, model, chat_id: int) -> int:
    with sessions() as s:
        return len(list(s.scalars(select(model).where(model.chat_id == chat_id))))


def handle(update: Update, telegram: ServerTelegram, sessions) -> None:
    handle_update(
        update,
        telegram,  # type: ignore[arg-type]
        settings(),
        sessions,
        FakeQueries(),  # type: ignore[arg-type]
        NOW,
    )


# --- 條件 1：不結束、update 被確認 ---


def test_command_reply_forbidden_does_not_raise(sessions):
    telegram = ServerTelegram([msg(1, BLOCKED)])

    handle(msg(1, BLOCKED), telegram, sessions)  # 不可拋 TelegramForbiddenError


def test_button_answer_forbidden_does_not_raise(sessions):
    telegram = ServerTelegram([], forbidden_chats=())
    telegram.answer_callback_query = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[method-assign]
        TelegramForbiddenError(BLOCKED)
    )

    handle(button(1, BLOCKED), telegram, sessions)


def test_button_edit_forbidden_does_not_raise(sessions):
    telegram = ServerTelegram([button(1, BLOCKED)])

    handle(button(1, BLOCKED), telegram, sessions)


def test_poll_command_forbidden_keeps_running_and_handles_next_update(sessions):
    telegram = ServerTelegram([msg(1, BLOCKED), msg(2, OTHER)])

    poll(telegram, sessions)

    assert OTHER in telegram.sent


def test_poll_button_forbidden_keeps_running_and_handles_next_update(sessions):
    telegram = ServerTelegram([button(1, BLOCKED), msg(2, OTHER)])

    poll(telegram, sessions)

    assert OTHER in telegram.sent


def test_poll_forbidden_update_is_acknowledged_not_redelivered(sessions):
    telegram = ServerTelegram([msg(1, BLOCKED)])

    poll(telegram, sessions)

    assert telegram.pending == []  # offset 已越過 update 1


# --- 條件 2：依 7.21 刪掉該 chat 的訂閱，其他 chat 不受影響 ---


@pytest.mark.parametrize("update", [msg(1, BLOCKED), button(1, BLOCKED)], ids=["command", "button"])
def test_poll_forbidden_chat_data_is_forgotten(sessions, update):
    telegram = ServerTelegram([update])

    poll(telegram, sessions)

    assert [rows(sessions, m, BLOCKED) for m in (Subscription, ChatSettings, MutedPost)] == [0] * 3


@pytest.mark.parametrize("update", [msg(1, BLOCKED), button(1, BLOCKED)], ids=["command", "button"])
def test_poll_forbidden_does_not_touch_other_chats(sessions, update):
    telegram = ServerTelegram([update, msg(2, OTHER)])

    poll(telegram, sessions)

    assert [rows(sessions, m, OTHER) for m in (Subscription, ChatSettings, MutedPost)] == [1] * 3


def test_handle_update_forbidden_command_forgets_chat(sessions):
    handle(msg(1, BLOCKED), ServerTelegram([]), sessions)

    assert rows(sessions, Subscription, BLOCKED) == 0


def test_handle_update_non_forbidden_chat_keeps_subscription(sessions):
    handle(msg(1, OTHER), ServerTelegram([]), sessions)

    assert rows(sessions, Subscription, OTHER) == 1


# --- 條件 3：H-1 重現（send_message 一律 403、模擬重啟兩次）---


def test_h1_repro_always_forbidden_two_restarts_never_die(sessions):
    pending = [msg(1, BLOCKED)]
    for _ in range(2):  # 重啟：offset 回到 None，Telegram 重送未確認的 update
        telegram = ServerTelegram(pending)
        poll(telegram, sessions)  # 不可拋例外
        pending = telegram.pending

    assert pending == []


def test_h1_repro_send_message_always_forbidden_for_any_chat(sessions):
    telegram = ServerTelegram([msg(1, BLOCKED), msg(2, OTHER), msg(3, 99)], forbidden_chats=())
    telegram.send_message = lambda chat_id, *a, **k: (_ for _ in ()).throw(  # type: ignore[method-assign]
        TelegramForbiddenError(chat_id)
    )

    poll(telegram, sessions)

    assert telegram.pending == []
    assert [rows(sessions, Subscription, c) for c in (BLOCKED, OTHER)] == [0, 0]

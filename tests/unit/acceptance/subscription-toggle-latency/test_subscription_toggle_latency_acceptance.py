"""驗收 subscription-toggle-latency（#82）：訂閱切換的呼叫順序、PG 查詢數、畫面與資料一致。

走 handle_update 全流程；PG 換成記憶體 SQLite（只建 boards、subscriptions），
用 engine 事件記下每一句 SQL，和 Telegram 呼叫放在同一條時間線上。
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from radar.bot.main import handle_update
from radar.bot.telegram import CallbackQuery, Update
from radar.bot.views import Action, encode_callback
from radar.common.db.models import Board, Subscription
from radar.common.log import log
from radar.common.settings import TelegramSettings

NOW = datetime(2026, 10, 29, 3, 0, tzinfo=UTC)
CHAT = 5
BOARDS = ["Gossiping", "Stock", "Tech_Job"]
# 現況量測：訂閱 6 句（enabled_boards、boards_of、get、INSERT、重畫 enabled_boards＋boards_of），
# 取消 5 句（少一句 get）；不含 COMMIT。上限取較大者。
MAX_SQL_PER_TOGGLE = 6


class Timeline:
    def __init__(self) -> None:
        self.events: list[str] = []

    def sql(self) -> list[str]:
        return [e for e in self.events if e.startswith("sql:")]


class FakeTelegram:
    def __init__(self, timeline: Timeline) -> None:
        self.timeline = timeline
        self.answers: list[tuple[str, str | None]] = []
        self.edits: list[tuple[int, int, str, object]] = []

    def answer_callback_query(self, callback_id, text=None):
        self.timeline.events.append("answer")
        self.answers.append((callback_id, text))

    def edit_message_text(self, chat_id, message_id, text, keyboard=None):
        self.timeline.events.append("edit")
        self.edits.append((chat_id, message_id, text, keyboard))

    def send_message(self, chat_id, text, keyboard=None):
        self.timeline.events.append("send")


class FakeQueries:
    def post_stats(self, post_ids):
        return {}

    def hot(self, boards):
        return []

    def overview(self, board, now):
        raise AssertionError("not used")


@pytest.fixture
def env():
    log.info("init")  # 先初始化 logger
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    Board.__table__.create(engine)
    Subscription.__table__.create(engine)
    sessions = sessionmaker(engine)
    with sessions() as s:
        for b in BOARDS:
            s.add(Board(board=b, enabled=True, interval_sec=60, recrawl_min_push=0))
        s.add(Board(board="Hidden", enabled=False, interval_sec=60, recrawl_min_push=0))
        s.commit()

    timeline = Timeline()

    @event.listens_for(engine, "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        timeline.events.append("sql:" + statement.split(None, 1)[0].upper())

    telegram = FakeTelegram(timeline)
    settings = TelegramSettings(bot_token="t", allowed_chat_ids=[CHAT], poll_timeout_s=1)

    def press(board: str, update_id: int = 1) -> None:
        data = encode_callback(Action.SUB, board)
        cb = CallbackQuery(id=f"cb{update_id}", chat_id=CHAT, message_id=77, data=data)
        handle_update(
            Update(update_id=update_id, callback=cb),
            telegram,  # type: ignore[arg-type]
            settings,
            sessions,
            FakeQueries(),  # type: ignore[arg-type]
            NOW,
        )

    def db_boards() -> list[str]:
        with sessions() as s:
            return sorted(
                s.scalars(select(Subscription.unit_key).where(Subscription.chat_id == CHAT))
            )

    def subscribe_directly(board: str) -> None:
        with sessions() as s:
            s.add(Subscription(chat_id=CHAT, unit_type="board", unit_key=board))
            s.commit()

    return press, telegram, timeline, db_boards, subscribe_directly


def _marks(telegram: FakeTelegram) -> dict[str, str]:
    """最後一次 editMessageText 的看板按鈕：看板 → ✅／⬜。"""
    keyboard = telegram.edits[-1][3]
    marks: dict[str, str] = {}
    for row in keyboard:  # type: ignore[attr-defined]
        for button in row:
            mark, _, name = button.text.partition(" ")
            if name in BOARDS:
                marks[name] = mark
    return marks


def _expected(subscribed: list[str]) -> dict[str, str]:
    return {b: ("✅" if b in subscribed else "⬜") for b in BOARDS}


# --- 呼叫順序 ---


@pytest.mark.parametrize("already_subscribed", [False, True])
def test_toggle_answers_before_edit_and_before_requery(env, already_subscribed):
    press, telegram, timeline, _db, subscribe_directly = env
    if already_subscribed:
        subscribe_directly("Stock")
    timeline.events.clear()

    press("Stock")

    events = timeline.events
    assert events.count("answer") == 1 and events.count("edit") == 1
    assert events.index("answer") < events.index("edit")
    write = next(i for i, e in enumerate(events) if e in ("sql:INSERT", "sql:DELETE"))
    after_write_queries = [
        i for i, e in enumerate(events) if i > write and e.startswith("sql:SELECT")
    ]
    answer = events.index("answer")
    assert all(answer < i for i in after_write_queries), events


def test_toggle_answer_carries_toast_for_subscribe_and_unsubscribe(env):
    press, telegram, *_ = env

    press("Stock", 1)
    press("Stock", 2)

    assert [a[1] for a in telegram.answers] == ["已訂閱 Stock", "已取消 Stock"]


# --- PG 查詢次數（守門：不比現況多）---


@pytest.mark.parametrize("already_subscribed", [False, True])
def test_toggle_sql_count_not_more_than_baseline(env, already_subscribed):
    press, _telegram, timeline, _db, subscribe_directly = env
    if already_subscribed:
        subscribe_directly("Stock")
    timeline.events.clear()

    press("Stock")

    assert len(timeline.sql()) <= MAX_SQL_PER_TOGGLE, timeline.sql()


# --- 畫面與資料一致 ---


def test_toggle_screen_marks_match_database_after_subscribe(env):
    press, telegram, _t, db_boards, _s = env

    press("Stock")

    assert db_boards() == ["Stock"]
    assert _marks(telegram) == _expected(["Stock"])


def test_toggle_screen_marks_match_database_after_unsubscribe(env):
    press, telegram, _t, db_boards, subscribe_directly = env
    subscribe_directly("Stock")
    subscribe_directly("Gossiping")

    press("Stock")

    assert db_boards() == ["Gossiping"]
    assert _marks(telegram) == _expected(["Gossiping"])


def test_toggle_twice_returns_to_original_state(env):
    press, telegram, _t, db_boards, subscribe_directly = env
    subscribe_directly("Gossiping")

    press("Stock", 1)
    assert _marks(telegram) == _expected(["Gossiping", "Stock"])
    press("Stock", 2)

    assert db_boards() == ["Gossiping"]
    assert _marks(telegram) == _expected(["Gossiping"])
    assert len(telegram.edits) == 2


def test_toggle_different_boards_keeps_each_mark_independent(env):
    press, telegram, _t, db_boards, _s = env

    press("Stock", 1)
    press("Tech_Job", 2)
    press("Stock", 3)

    assert db_boards() == ["Tech_Job"]
    assert _marks(telegram) == _expected(["Tech_Job"])


def test_toggle_unknown_or_disabled_board_does_not_change_data(env):
    press, telegram, _t, db_boards, _s = env

    press("Hidden", 1)
    press("Nope", 2)

    assert db_boards() == []
    assert [a[1] for a in telegram.answers] == ["找不到看板 Hidden", "找不到看板 Nope"]
    assert telegram.edits == []

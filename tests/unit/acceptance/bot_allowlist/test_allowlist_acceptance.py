"""驗收 bot-allowlist-required（D-010、資安 M-1、開發規格 7.21）。

只走對外入口 main()（啟動檢查）與 handle_update（回應範圍）；外部連線全部換成 fake。
清單與 TELEGRAM_ALLOW_ALL 同時設定時，本測試鎖定「清單優先、仍受限制」並要求啟動警告。
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from radar.bot import main as bot_main
from radar.bot.telegram import CallbackQuery, IncomingMessage, Update
from radar.common.settings import TelegramSettings

NOW = datetime(2026, 10, 20, 3, 0, tzinfo=UTC)
LISTED = 111
STRANGER = 999


class RecordingLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _add(self, level: str, msg: object, *args: object) -> None:
        text = str(msg)
        try:
            text = text % args if args else text
        except (TypeError, ValueError):
            text = f"{text} {args}"
        self.records.append((level, text))

    def debug(self, msg, *a, **k):
        self._add("DEBUG", msg, *a)

    def info(self, msg, *a, **k):
        self._add("INFO", msg, *a)

    def warning(self, msg, *a, **k):
        self._add("WARNING", msg, *a)

    warn = warning

    def error(self, msg, *a, **k):
        self._add("ERROR", msg, *a)

    def critical(self, msg, *a, **k):
        self._add("CRITICAL", msg, *a)

    def exception(self, msg, *a, **k):
        self._add("ERROR", msg, *a)


class FakeTelegram:
    def __init__(self, settings=None) -> None:
        self.settings = settings
        self.sent: list[int] = []
        self.answered: list[str] = []
        self.edited: list[int] = []

    def send_message(self, chat_id, text, keyboard=None):
        self.sent.append(chat_id)

    def edit_message_text(self, chat_id, message_id, text, keyboard=None):
        self.edited.append(chat_id)

    def answer_callback_query(self, callback_id, text=None):
        self.answered.append(callback_id)

    def set_my_commands(self, commands):
        pass

    def close(self):
        pass


class FakeQueries:
    def post_stats(self, post_ids):
        return {}

    def hot(self, boards):
        return []

    def overview(self, board, now):
        return None


class _Sessions:
    """handle_update 的指令路徑會開 session；選單畫面不需要資料。"""

    def __call__(self):
        raise AssertionError("no DB expected in this test")


@pytest.fixture
def started(monkeypatch):
    """替換 main() 的所有外部連線；回傳 (log, telegram 清單)。"""
    rec = RecordingLog()
    clients: list[FakeTelegram] = []
    connected: list[str] = []

    def telegram_factory(settings):
        client = FakeTelegram(settings)
        clients.append(client)
        return client

    def connect(name):
        def _f(*a, **k):
            connected.append(name)
            return SimpleNamespace(
                close=lambda: None,
                flush=lambda: None,
                dispose=lambda: None,
                run=lambda: None,
                stop=lambda: None,
            )

        return _f

    monkeypatch.setattr(bot_main, "log", rec)
    monkeypatch.setattr(bot_main, "setup_logging", lambda name: None)
    monkeypatch.setattr(bot_main, "make_engine", connect("pg"))
    monkeypatch.setattr(bot_main, "make_session_factory", lambda e: _Sessions())
    monkeypatch.setattr(bot_main, "ClickHouseClient", connect("ch"))
    monkeypatch.setattr(bot_main, "ClickHouseQueries", lambda *a, **k: FakeQueries())
    monkeypatch.setattr(bot_main, "JsonProducer", connect("kafka"))
    monkeypatch.setattr(bot_main, "BatchConsumer", connect("consumer"))
    monkeypatch.setattr(bot_main, "get_postgres_settings", lambda: None)
    monkeypatch.setattr(bot_main, "get_kafka_settings", lambda: None)
    monkeypatch.setattr(bot_main, "ClickHouseSettings", lambda: None)
    monkeypatch.setattr(bot_main, "TelegramClient", telegram_factory)
    monkeypatch.setattr(bot_main, "poll_commands", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_ALL", raising=False)
    return SimpleNamespace(log=rec, clients=clients, connected=connected)


def run_main(started) -> TelegramSettings:
    bot_main.main()
    assert started.clients, "main() 沒有建立 TelegramClient"
    return started.clients[0].settings


def assert_start_refused(started) -> None:
    with pytest.raises((Exception, SystemExit)) as exc:
        bot_main.main()
    message = str(exc.value) + " ".join(text for _, text in started.log.records)
    assert "TELEGRAM_ALLOWED_CHAT_IDS" in message
    assert "TELEGRAM_ALLOW_ALL" in message
    assert started.connected == [], "拒絕啟動前不可連任何外部服務"


def message_update(update_id: int, chat_id: int) -> Update:
    return Update(update_id=update_id, message=IncomingMessage(chat_id=chat_id, text="/start"))


def button_update(update_id: int, chat_id: int) -> Update:
    cb = CallbackQuery(id=f"cb{update_id}", chat_id=chat_id, message_id=9, data="1:menu:")
    return Update(update_id=update_id, callback=cb)


def responded_chats(
    settings: TelegramSettings, chat_ids: list[int]
) -> dict[int, tuple[bool, bool]]:
    """各 chat 對「訊息」「按鈕」是否有任何回應。"""
    out: dict[int, tuple[bool, bool]] = {}
    for i, chat in enumerate(chat_ids):
        tg = FakeTelegram()
        sessions = _MenuSessions()
        bot_main.handle_update(message_update(i, chat), tg, settings, sessions, FakeQueries(), NOW)  # type: ignore[arg-type]
        msg_replied = bool(tg.sent)
        tg2 = FakeTelegram()
        bot_main.handle_update(button_update(i, chat), tg2, settings, sessions, FakeQueries(), NOW)  # type: ignore[arg-type]
        out[chat] = (msg_replied, bool(tg2.answered))
    return out


class _MenuSessions:
    """用記憶體 SQLite 提供 session，讓真正的指令與按鈕處理能跑。"""

    def __init__(self) -> None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from radar.common.db.models import ChatSettings, MutedPost, Subscription

        engine = create_engine(
            "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
        )
        for model in (Subscription, ChatSettings, MutedPost):
            model.__table__.create(engine)
        self._factory = sessionmaker(engine)

    def __call__(self):
        return self._factory()


# --- 驗收條件 1：沒設／空且未明確開放 → 啟動失敗 ---


def test_main_allowlist_unset_refuses_to_start(started):
    assert_start_refused(started)


def test_main_allowlist_empty_string_refuses_to_start(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "")

    assert_start_refused(started)


def test_main_allowlist_only_separators_refuses_to_start(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", " , ,")

    assert_start_refused(started)


@pytest.mark.parametrize("value", ["false", "False", "0"])
def test_main_allow_all_not_true_refuses_to_start(started, monkeypatch, value):
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", value)

    assert_start_refused(started)


# --- 驗收條件 2：清單有值只回應清單內；ALLOW_ALL=true 回應所有人並警告 ---


def test_main_allowlist_set_responds_only_to_listed_chat(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", f"{LISTED}, -100456")

    settings = run_main(started)
    result = responded_chats(settings, [LISTED, -100456, STRANGER])

    assert result[LISTED] == (True, True)
    assert result[-100456] == (True, True)
    assert result[STRANGER] == (False, False)


def test_main_allowlist_set_without_allow_all_logs_no_open_warning(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", str(LISTED))

    run_main(started)

    assert not [r for r in started.log.records if "ALLOW_ALL" in r[1]]


def test_main_allow_all_true_responds_to_every_chat(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", "true")

    settings = run_main(started)
    result = responded_chats(settings, [LISTED, STRANGER])

    assert result[LISTED] == (True, True)
    assert result[STRANGER] == (True, True)


def test_main_allow_all_true_logs_warning_naming_variable(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", "true")

    run_main(started)

    warnings = [
        text
        for level, text in started.log.records
        if level in {"WARNING", "ERROR", "CRITICAL"} and "TELEGRAM_ALLOW_ALL" in text
    ]
    assert warnings, started.log.records


# --- 驗收條件 3：清單有值又 ALLOW_ALL=true → 清單優先（仍受限制），並警告 ---


def test_main_list_and_allow_all_keeps_restriction_to_list(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", str(LISTED))
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", "true")

    settings = run_main(started)
    result = responded_chats(settings, [LISTED, STRANGER])

    assert result[LISTED] == (True, True)
    assert result[STRANGER] == (False, False)


def test_main_list_and_allow_all_logs_warning_about_conflict(started, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", str(LISTED))
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", "true")

    run_main(started)

    warnings = [
        text
        for level, text in started.log.records
        if level in {"WARNING", "ERROR", "CRITICAL"} and "TELEGRAM_ALLOW_ALL" in text
    ]
    assert warnings, started.log.records

"""驗收 bot-push-allowlist（#121、資安 v0.7.0 L-6、D-010）。

只走 main() 組出的警示 handler：外部連線全換成 fake，檢查實際推送給哪些 chat、
訂閱資料有沒有被動到、被過濾的人數有沒有記 log。
"""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from radar.bot import main as bot_main
from radar.common.schemas import Alert

NOW = datetime(2026, 10, 29, 3, 0, tzinfo=UTC)
SUBSCRIBERS = [111, 222, 777, 888, 999]


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
        self.sent: list[int] = []

    def send_message(self, chat_id, text, keyboard=None):
        self.sent.append(chat_id)

    def set_my_commands(self, commands):
        pass

    def close(self):
        pass


class FakeQueries:
    def post_stats(self, post_ids):
        return {}


class FakePrefs:
    """PG 訂閱資料：recipients 回傳全部訂閱者；任何其他呼叫都記下來（不應該有）。"""

    calls: list[str] = []

    def __init__(self, _session) -> None:
        pass

    def recipients(self, alert):
        FakePrefs.calls.append("recipients")
        return list(SUBSCRIBERS)

    def __getattr__(self, name):
        def _other(*a, **k):
            FakePrefs.calls.append(name)

        return _other


class _Session:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _sessions():
    return _Session()


@pytest.fixture
def bot(monkeypatch):
    rec = RecordingLog()
    telegrams: list[FakeTelegram] = []
    captured: dict[str, object] = {}
    FakePrefs.calls = []

    def telegram_factory(settings):
        client = FakeTelegram(settings)
        telegrams.append(client)
        return client

    def consumer_factory(*a, **k):
        captured["handler"] = k["handler"]
        return SimpleNamespace(run=lambda: None, stop=lambda: None)

    def closeable(*a, **k):
        return SimpleNamespace(close=lambda: None, flush=lambda: None, dispose=lambda: None)

    monkeypatch.setattr(bot_main, "log", rec)
    monkeypatch.setattr(bot_main, "setup_logging", lambda name: None)
    monkeypatch.setattr(bot_main, "make_engine", closeable)
    monkeypatch.setattr(bot_main, "make_session_factory", lambda e: _sessions)
    monkeypatch.setattr(bot_main, "ClickHouseClient", closeable)
    monkeypatch.setattr(bot_main, "ClickHouseQueries", lambda *a, **k: FakeQueries())
    monkeypatch.setattr(bot_main, "JsonProducer", closeable)
    monkeypatch.setattr(bot_main, "BatchConsumer", consumer_factory)
    monkeypatch.setattr(bot_main, "DlqPublisher", lambda *a, **k: None)
    monkeypatch.setattr(bot_main, "get_postgres_settings", lambda: None)
    monkeypatch.setattr(bot_main, "get_kafka_settings", lambda: None)
    monkeypatch.setattr(bot_main, "ClickHouseSettings", lambda: None)
    monkeypatch.setattr(bot_main, "TelegramClient", telegram_factory)
    monkeypatch.setattr(bot_main, "PreferenceRepository", FakePrefs)
    monkeypatch.setattr(bot_main, "poll_commands", lambda *a, **k: None)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("TELEGRAM_ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("TELEGRAM_ALLOW_ALL", raising=False)
    return SimpleNamespace(log=rec, telegrams=telegrams, captured=captured)


def alert() -> Alert:
    return Alert(
        alert_id=uuid4(),
        unit_type="board",
        unit_key="Gossiping",
        board="Gossiping",
        window_start=NOW,
        window_end=NOW,
        value=10,
        baseline=1.0,
        zscore=5.0,
        sample_post_ids=[],
        created_at=NOW,
    )


def push(bot) -> list[int]:
    """啟動 main()，把一則警示交給它組出的 handler，回傳實際收到推送的 chat。"""
    bot_main.main()
    bot.log.records.clear()
    bot.captured["handler"]([alert()])
    return bot.telegrams[0].sent


def test_push_with_allowlist_reaches_only_listed_chats(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111,222")

    assert sorted(push(bot)) == [111, 222]


def test_push_with_allowlist_does_not_touch_subscription_data(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111,222")

    push(bot)

    assert set(FakePrefs.calls) == {"recipients"}


def test_push_with_allowlist_matching_no_subscriber_sends_nothing(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "5,6")

    assert push(bot) == []
    assert set(FakePrefs.calls) == {"recipients"}


def test_push_with_allowlist_covering_everyone_sends_to_all(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", ",".join(str(c) for c in SUBSCRIBERS))

    assert sorted(push(bot)) == SUBSCRIBERS


def test_push_with_allow_all_and_no_list_reaches_every_subscriber(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", "true")

    assert sorted(push(bot)) == SUBSCRIBERS


def test_push_with_allow_all_and_list_still_filters_by_list(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOW_ALL", "true")
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111")

    assert push(bot) == [111]


def test_push_filtering_logs_filtered_count_at_info_or_debug(bot, monkeypatch):
    monkeypatch.setenv("TELEGRAM_ALLOWED_CHAT_IDS", "111,222")

    push(bot)

    # 5 個訂閱者、2 個在清單 → 過濾 3 個
    filtered = [t for lvl, t in bot.log.records if lvl in ("INFO", "DEBUG") and "3" in t]
    assert filtered, f"沒有記被過濾的人數: {bot.log.records}"
    assert all(lvl not in ("WARNING", "ERROR", "CRITICAL") for lvl, _ in bot.log.records)

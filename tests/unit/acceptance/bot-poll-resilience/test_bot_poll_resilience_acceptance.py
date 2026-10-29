"""bot-poll-resilience 驗收測試（#79、#67）：只測 poll_commands 與 TelegramClient 的對外行為。"""

import threading
from datetime import UTC, datetime

import httpx2
import pytest
from sqlalchemy.exc import OperationalError

from radar.bot import main as bot_main
from radar.bot.main import poll_commands
from radar.bot.telegram import IncomingMessage, TelegramClient, Update
from radar.common.kafka.consumer import TransientError
from radar.common.log import log
from radar.common.settings import TelegramSettings

NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)
# 退避上限的容許值：比現行 30 秒寬，但遠小於 #67 的長時間無反應
MAX_BACKOFF_S = 60.0


def pg_down() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


def msg(update_id: int) -> Update:
    return Update(update_id=update_id, message=IncomingMessage(chat_id=5, text="/start"))


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeQueries:
    def post_stats(self, post_ids):
        return {}

    def hot(self, boards):
        return []


class FakeTelegram:
    def __init__(self, batches, stop, send_errors=()):
        self.batches = list(batches)
        self.stop = stop
        self.offsets: list[int | None] = []
        self.sent: list[int] = []
        self.send_errors = list(send_errors)

    def get_updates(self, offset, timeout_s):
        self.offsets.append(offset)
        if not self.batches:
            self.stop.set()
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch

    def send_message(self, chat_id, text, keyboard=None):
        if self.send_errors:
            raise self.send_errors.pop(0)
        self.sent.append(chat_id)

    def edit_message_text(self, *args, **kwargs):
        pass

    def answer_callback_query(self, *args, **kwargs):
        pass


def settings() -> TelegramSettings:
    return TelegramSettings(bot_token="t", allowed_chat_ids=[], poll_timeout_s=1)


def run(batches, send_errors=()):
    stop = threading.Event()
    telegram = FakeTelegram(batches, stop, send_errors)
    waits: list[float] = []
    poll_commands(
        telegram,  # type: ignore[arg-type]
        settings(),
        lambda: FakeSession(),  # type: ignore[arg-type, return-value]
        FakeQueries(),
        stop,
        wait=lambda s: waits.append(s) or False,
        clock=lambda: NOW,
    )
    return telegram, waits


@pytest.fixture
def warnings(caplog):
    # loggerhelper 第一次寫 log 才建 logger；先建好 caplog 才掛得上（見仲裁檔）
    log.debug("init logger")
    caplog.set_level("WARNING")
    return caplog


# --- PG 斷線是暫時性錯誤 ---


def test_purge_pg_down_loop_keeps_running_and_logs_warning(monkeypatch, warnings):
    calls: list[int] = []

    def purge(_sessions, _settings, _now):
        calls.append(1)
        if len(calls) == 1:
            raise pg_down()
        return 0

    monkeypatch.setattr(bot_main, "purge_muted", purge)

    telegram, _ = run([[msg(1)], [msg(2)]])

    assert telegram.sent == [5, 5]
    assert any(r.levelname == "WARNING" for r in warnings.records)


def test_purge_pg_down_retried_on_next_round_not_after_full_interval(monkeypatch):
    calls: list[int] = []

    def purge(_sessions, _settings, _now):
        calls.append(1)
        if len(calls) == 1:
            raise pg_down()
        return 0

    monkeypatch.setattr(bot_main, "purge_muted", purge)

    run([[], []])

    assert len(calls) >= 2


def test_purge_pg_down_forever_still_handles_commands(monkeypatch):
    def purge(_sessions, _settings, _now):
        raise pg_down()

    monkeypatch.setattr(bot_main, "purge_muted", purge)

    telegram, _ = run([[msg(1)], [msg(2)]])

    assert telegram.sent == [5, 5]
    assert telegram.offsets[-1] == 3


def test_update_pg_down_loop_does_not_abort_and_recovers(monkeypatch):
    monkeypatch.setattr(bot_main, "purge_muted", lambda *_a: 0)

    # PG 斷線時重試或略過皆可，但迴圈不可中止，恢復後要能回覆
    telegram, _ = run([[msg(1)], [msg(1)], [msg(2)]], send_errors=[pg_down()])

    assert len(telegram.sent) >= 2


# --- 單筆 update 的意外例外 ---


def test_update_unexpected_error_is_skipped_and_offset_advances(monkeypatch):
    monkeypatch.setattr(bot_main, "purge_muted", lambda *_a: 0)

    telegram, _ = run([[msg(10)], []], send_errors=[RuntimeError("bug")])

    assert telegram.offsets[:2] == [None, 11]


def test_update_unexpected_error_does_not_block_rest_of_batch(monkeypatch):
    monkeypatch.setattr(bot_main, "purge_muted", lambda *_a: 0)

    telegram, _ = run([[msg(10), msg(11)]], send_errors=[ValueError("bad")])

    assert telegram.sent == [5]
    assert telegram.offsets[1] == 12


def test_update_unexpected_error_is_logged(monkeypatch, warnings):
    monkeypatch.setattr(bot_main, "purge_muted", lambda *_a: 0)

    run([[msg(10)]], send_errors=[RuntimeError("boom-marker")])

    assert any("boom-marker" in r.getMessage() for r in warnings.records)


# --- Telegram 網路錯誤的退避 ---


def test_network_errors_backoff_is_capped_and_recovers_next_round(monkeypatch):
    monkeypatch.setattr(bot_main, "purge_muted", lambda *_a: 0)
    errors = [TransientError("telegram getUpdates connection error: ReadTimeout")] * 30

    telegram, waits = run([*errors, [msg(1)]])

    assert len(waits) == 30
    assert max(waits) <= MAX_BACKOFF_S
    assert telegram.sent == [5]


@pytest.mark.parametrize("exc", [httpx2.ReadTimeout("t"), httpx2.ConnectError("c")])
def test_client_network_error_becomes_transient_error_without_token(exc):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise exc

    client = TelegramClient(
        TelegramSettings(bot_token="SECRET-TOKEN", poll_timeout_s=1),
        transport=httpx2.MockTransport(handler),
    )

    with pytest.raises(TransientError) as info:
        client.get_updates(None, 1)

    assert "SECRET-TOKEN" not in str(info.value)

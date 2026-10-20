import threading
from datetime import UTC, datetime, timedelta

import pytest

from radar.bot import main as bot_main
from radar.bot.commands import COMMANDS
from radar.bot.main import (
    PURGE_INTERVAL,
    handle_update,
    is_allowed,
    poll_commands,
    purge_muted,
    register_commands,
    reply_to,
)
from radar.bot.telegram import (
    CallbackQuery,
    IncomingMessage,
    TelegramBadRequestError,
    Update,
)
from radar.common.kafka.consumer import TransientError
from radar.common.settings import TelegramSettings

NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def no_purge(monkeypatch):
    """poll_commands 每輪都可能清「不再通知」；FakeSession 不能執行 SQL。"""
    monkeypatch.setattr(bot_main, "purge_muted", lambda *_args: 0)


def settings(allowed=()) -> TelegramSettings:
    return TelegramSettings(bot_token="t", allowed_chat_ids=list(allowed), poll_timeout_s=1)


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

    def overview(self, board, now):
        raise AssertionError("not used")


class FakeTelegram:
    """依序回傳 batches 的每一批；用完後設 stop。"""

    def __init__(self, batches=(), stop: threading.Event | None = None, error=None):
        self.batches = list(batches)
        self.stop = stop or threading.Event()
        self.offsets: list[int | None] = []
        self.sent: list[tuple[int, str]] = []
        self.edited: list[tuple[int, int, str]] = []
        self.answered: list[tuple[str, str | None]] = []
        self.error = error

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
        if self.error is not None:
            raise self.error
        self.sent.append((chat_id, text))

    def edit_message_text(self, chat_id, message_id, text, keyboard=None):
        if self.error is not None:
            raise self.error
        self.edited.append((chat_id, message_id, text))

    def answer_callback_query(self, callback_id, text=None):
        self.answered.append((callback_id, text))


def msg(update_id: int, chat_id: int | None = 5, text: str | None = "/start") -> Update:
    return Update(update_id=update_id, message=IncomingMessage(chat_id=chat_id, text=text))


def button(update_id: int, chat_id: int | None = 5, data: str = "1:menu:") -> Update:
    callback = CallbackQuery(id=f"cb{update_id}", chat_id=chat_id, message_id=77, data=data)
    return Update(update_id=update_id, callback=callback)


def run(batches, allowed=(), error=None):
    stop = threading.Event()
    telegram = FakeTelegram(batches, stop, error)
    waits: list[float] = []
    poll_commands(
        telegram,  # type: ignore[arg-type]
        settings(allowed),
        lambda: FakeSession(),  # type: ignore[arg-type, return-value]
        FakeQueries(),
        stop,
        wait=lambda s: waits.append(s) or False,
        clock=lambda: NOW,
    )
    return telegram, waits


def handle(update: Update, allowed=(), error=None) -> FakeTelegram:
    telegram = FakeTelegram(error=error)
    handle_update(
        update,
        telegram,  # type: ignore[arg-type]
        settings(allowed),
        lambda: FakeSession(),  # type: ignore[arg-type, return-value]
        FakeQueries(),
        NOW,
    )
    return telegram


# --- is_allowed ---


def test_is_allowed_empty_list_allows_all():
    assert is_allowed(123, []) is True


def test_is_allowed_rejects_unlisted_chat():
    assert (is_allowed(1, [1, 2]), is_allowed(3, [1, 2])) == (True, False)


def test_is_allowed_none_chat_rejected():
    assert is_allowed(None, []) is False


# --- reply_to ---


def test_reply_to_non_command_returns_none():
    message = IncomingMessage(chat_id=5, text="hi")

    assert reply_to(message, lambda: FakeSession(), FakeQueries(), 0.6) is None  # type: ignore[arg-type]


# --- handle_update（S6-04） ---


def test_handle_update_command_replies_with_menu():
    telegram = handle(msg(1))

    assert [c for c, _ in telegram.sent] == [5]


def test_handle_update_disallowed_message_ignored():
    assert handle(msg(1, chat_id=99), allowed=[5]).sent == []


def test_handle_update_callback_answers_then_edits_same_message():
    telegram = handle(button(1))

    assert telegram.answered == [("cb1", None)]
    assert [(c, m) for c, m, _ in telegram.edited] == [(5, 77)]


def test_handle_update_expired_callback_shows_menu_again():
    telegram = handle(button(1, data="0:menu:"))

    assert telegram.answered == [("cb1", None)]
    assert "過期" in telegram.edited[0][2]


def test_handle_update_disallowed_callback_not_answered():
    telegram = handle(button(1, chat_id=99), allowed=[5])

    assert (telegram.answered, telegram.edited) == ([], [])


def test_handle_update_edit_bad_request_is_skipped():
    telegram = handle(button(1), error=TelegramBadRequestError("message to edit not found"))

    assert telegram.answered == [("cb1", None)]


def test_handle_update_other_update_type_is_noop():
    telegram = handle(Update(update_id=1))

    assert (telegram.sent, telegram.edited, telegram.answered) == ([], [], [])


# --- poll_commands ---


def test_poll_commands_replies_and_advances_offset():
    telegram, _ = run([[msg(10), msg(11, text="hello")]])

    assert [c for c, _ in telegram.sent] == [5]
    assert telegram.offsets == [None, 12]


def test_poll_commands_advances_offset_past_ignored_updates():
    telegram, _ = run([[msg(10, chat_id=99)]], allowed=[5])

    assert telegram.sent == []
    assert telegram.offsets == [None, 11]


def test_poll_commands_transient_error_waits_and_continues():
    telegram, waits = run([TransientError("429", retry_after_s=3), [msg(1)]])

    assert waits == [3]
    assert [c for c, _ in telegram.sent] == [5]


def test_poll_commands_bad_request_reply_is_skipped():
    telegram, _ = run([[msg(1)]], error=TelegramBadRequestError("too long"))

    assert telegram.offsets == [None, 2]


def test_poll_commands_stops_when_event_set():
    stop = threading.Event()
    stop.set()
    telegram = FakeTelegram([[msg(1)]], stop)

    poll_commands(telegram, settings(), lambda: FakeSession(), FakeQueries(), stop)  # type: ignore[arg-type]

    assert telegram.offsets == []


def test_poll_commands_purges_muted_at_most_once_per_interval(monkeypatch):
    calls: list[datetime] = []
    monkeypatch.setattr(bot_main, "purge_muted", lambda _s, _set, now: calls.append(now) or 0)
    times = iter([NOW, NOW + timedelta(minutes=1), NOW + PURGE_INTERVAL])
    stop = threading.Event()
    telegram = FakeTelegram([[], [], []], stop)

    poll_commands(
        telegram,  # type: ignore[arg-type]
        settings(),
        lambda: FakeSession(),  # type: ignore[arg-type, return-value]
        FakeQueries(),
        stop,
        clock=lambda: next(times, NOW + PURGE_INTERVAL),
    )

    assert calls == [NOW, NOW + PURGE_INTERVAL]


# --- register_commands ---


class CommandsTelegram:
    def __init__(self, error=None) -> None:
        self.commands = None
        self.error = error

    def set_my_commands(self, commands):
        if self.error is not None:
            raise self.error
        self.commands = commands


def test_register_commands_sends_command_list():
    telegram = CommandsTelegram()

    register_commands(telegram)  # type: ignore[arg-type]

    assert telegram.commands == COMMANDS


@pytest.mark.parametrize("error", [TransientError("502"), TelegramBadRequestError("bad")])
def test_register_commands_failure_does_not_raise(error):
    register_commands(CommandsTelegram(error))  # type: ignore[arg-type]


# --- purge_muted ---


def test_purge_muted_deletes_rows_older_than_retention(monkeypatch):
    befores: list[datetime] = []

    class FakePrefs:
        def __init__(self, _session) -> None:
            pass

        def purge_muted(self, before):
            befores.append(before)
            return 2

    monkeypatch.setattr(bot_main, "PreferenceRepository", FakePrefs)

    deleted = purge_muted(lambda: FakeSession(), settings(), NOW)  # type: ignore[arg-type]

    assert (deleted, befores) == (2, [NOW - timedelta(hours=48)])

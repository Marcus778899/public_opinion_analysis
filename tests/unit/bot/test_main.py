import threading

from radar.bot.main import is_allowed, poll_commands, reply_to
from radar.bot.telegram import IncomingMessage, TelegramBadRequestError
from radar.common.kafka.consumer import TransientError
from radar.common.settings import TelegramSettings


def settings(allowed=()) -> TelegramSettings:
    return TelegramSettings(bot_token="t", allowed_chat_ids=list(allowed), poll_timeout_s=1)


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeTelegram:
    """依序回傳 batches 的每一批；用完後設 stop。"""

    def __init__(self, batches, stop: threading.Event, reply_error: Exception | None = None):
        self.batches = list(batches)
        self.stop = stop
        self.offsets: list[int | None] = []
        self.sent: list[tuple[int, str]] = []
        self.reply_error = reply_error

    def get_updates(self, offset, timeout_s):
        self.offsets.append(offset)
        if not self.batches:
            self.stop.set()
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch

    def send_message(self, chat_id, text):
        if self.reply_error is not None:
            raise self.reply_error
        self.sent.append((chat_id, text))


def msg(update_id: int, chat_id: int | None = 5, text: str | None = "/start") -> IncomingMessage:
    return IncomingMessage(update_id=update_id, chat_id=chat_id, text=text)


def run(batches, allowed=(), reply_error=None):
    stop = threading.Event()
    telegram = FakeTelegram(batches, stop, reply_error)
    waits: list[float] = []
    poll_commands(
        telegram,  # type: ignore[arg-type]
        settings(allowed),
        lambda: FakeSession(),  # type: ignore[arg-type, return-value]
        lambda: [],
        stop,
        wait=lambda s: waits.append(s) or False,
    )
    return telegram, waits


# --- is_allowed ---


def test_is_allowed_empty_list_allows_all():
    assert is_allowed(123, []) is True


def test_is_allowed_rejects_unlisted_chat():
    assert (is_allowed(1, [1, 2]), is_allowed(3, [1, 2])) == (True, False)


def test_is_allowed_none_chat_rejected():
    assert is_allowed(None, []) is False


# --- reply_to ---


def test_reply_to_non_command_returns_none():
    assert reply_to(msg(1, text="hi"), lambda: FakeSession(), lambda: []) is None  # type: ignore[arg-type]


# --- poll_commands ---


def test_poll_commands_replies_and_advances_offset():
    telegram, _ = run([[msg(10), msg(11, text="hello")]])

    assert [c for c, _ in telegram.sent] == [5]
    assert telegram.offsets == [None, 12]


def test_poll_commands_ignores_disallowed_chat():
    telegram, _ = run([[msg(10, chat_id=99)]], allowed=[5])

    assert telegram.sent == []
    assert telegram.offsets == [None, 11]


def test_poll_commands_transient_error_waits_and_continues():
    telegram, waits = run([TransientError("429", retry_after_s=3), [msg(1)]])

    assert waits == [3]
    assert [c for c, _ in telegram.sent] == [5]


def test_poll_commands_bad_request_reply_is_skipped():
    telegram, _ = run([[msg(1)]], reply_error=TelegramBadRequestError("too long"))

    assert telegram.offsets == [None, 2]


def test_poll_commands_stops_when_event_set():
    stop = threading.Event()
    stop.set()
    telegram = FakeTelegram([[msg(1)]], stop)

    poll_commands(telegram, settings(), lambda: FakeSession(), lambda: [], stop)  # type: ignore[arg-type]

    assert telegram.offsets == []

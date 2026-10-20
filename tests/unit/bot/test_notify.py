import uuid
from datetime import UTC, datetime, timedelta

import pytest

from radar.bot.notify import AlertNotifier, SentAlerts, safe_stats, stats_post_ids
from radar.bot.stats import PostStats
from radar.bot.telegram import Button, TelegramBadRequestError, TelegramForbiddenError
from radar.bot.views import Screen
from radar.common.clickhouse import ClickHouseError
from radar.common.kafka.consumer import TransientError
from radar.common.schemas import Alert

PID = "Stock.M.1792000000.A.ABC"
PID2 = "Stock.M.1792000001.A.DEF"
NOW = datetime(2026, 10, 17, 3, 0, tzinfo=UTC)


def alert(unit_type="post", samples=(PID,), board="Stock", n=1) -> Alert:
    return Alert(
        alert_id=uuid.UUID(int=n),
        unit_type=unit_type,
        unit_key=PID if unit_type == "post" else board,
        board=board,
        window_start=NOW - timedelta(minutes=10),
        window_end=NOW,
        value=45,
        baseline=3.2,
        zscore=8.04,
        sample_post_ids=list(samples),
        created_at=NOW,
    )


class FakeTelegram:
    def __init__(self, fail: dict[int, Exception] | None = None) -> None:
        self.sent: list[tuple[int, str]] = []
        self.keyboards: list = []
        self.fail = fail or {}

    def send_message(self, chat_id, text, keyboard=None):
        if chat_id in self.fail:
            raise self.fail.pop(chat_id)
        self.sent.append((chat_id, text))
        self.keyboards.append(keyboard)


KEYBOARD = [[Button("開啟原文", url="https://www.ptt.cc/")]]


def notifier(telegram, chats=(1, 2), forgotten=None):
    forgotten = forgotten if forgotten is not None else []
    return AlertNotifier(
        telegram,
        recipients=lambda _alert: list(chats),
        render=lambda a: Screen(f"alert {a.unit_key}", KEYBOARD),
        forget_chat=forgotten.append,
    )


# --- SentAlerts ---


def test_sent_alerts_seen_after_add():
    sent = SentAlerts()
    sent.add("a")

    assert (sent.seen("a"), sent.seen("b")) == (True, False)


def test_sent_alerts_evicts_oldest():
    sent = SentAlerts(max_size=2)
    for key in ("a", "b", "c"):
        sent.add(key)

    assert (sent.seen("a"), sent.seen("c")) == (False, True)


# --- stats_post_ids / safe_stats（S6-05） ---


def test_stats_post_ids_post_alert_is_the_post():
    assert stats_post_ids(alert("post", (PID, PID2))) == [PID]


def test_stats_post_ids_board_alert_takes_first_three_samples():
    samples = tuple(f"Stock.M.179200000{i}.A.ABC" for i in range(5))

    assert stats_post_ids(alert("board", samples)) == list(samples[:3])


def stats_of(post_id: str) -> PostStats:
    return PostStats(post_id, "Stock", "t", 1, 0, 0, None)


def test_safe_stats_returns_query_result():
    assert safe_stats(lambda ids: {i: stats_of(i) for i in ids}, [PID]) == {PID: stats_of(PID)}


def test_safe_stats_clickhouse_error_returns_empty():
    def boom(_ids):
        raise ClickHouseError("500: down")

    assert safe_stats(boom, [PID]) == {}


def test_safe_stats_other_error_propagates():
    def boom(_ids):
        raise KeyError("bug")

    with pytest.raises(KeyError):
        safe_stats(boom, [PID])


# --- AlertNotifier ---


def test_notifier_sends_to_every_subscribed_chat():
    telegram = FakeTelegram()

    notifier(telegram)([alert()])

    assert [c for c, _ in telegram.sent] == [1, 2]


def test_notifier_sends_rendered_text_and_keyboard():
    telegram = FakeTelegram()

    notifier(telegram, chats=(1,))([alert()])

    assert telegram.sent == [(1, f"alert {PID}")]
    assert telegram.keyboards == [KEYBOARD]


def test_notifier_no_subscribers_sends_nothing():
    telegram = FakeTelegram()

    notifier(telegram, chats=())([alert()])

    assert telegram.sent == []


def test_notifier_duplicate_alert_sent_once():
    telegram = FakeTelegram()
    handler = notifier(telegram, chats=(1,))

    handler([alert(), alert()])
    handler([alert()])

    assert len(telegram.sent) == 1


def test_notifier_forbidden_chat_is_forgotten_and_others_still_sent():
    telegram = FakeTelegram(fail={1: TelegramForbiddenError(1)})
    forgotten: list[int] = []

    notifier(telegram, forgotten=forgotten)([alert()])

    assert forgotten == [1]
    assert [c for c, _ in telegram.sent] == [2]


def test_notifier_bad_request_is_skipped():
    telegram = FakeTelegram(fail={1: TelegramBadRequestError("bad")})

    notifier(telegram)([alert()])

    assert [c for c, _ in telegram.sent] == [2]


def test_notifier_transient_error_propagates():
    telegram = FakeTelegram(fail={2: TransientError("502")})

    with pytest.raises(TransientError):
        notifier(telegram)([alert()])


def test_notifier_retry_after_partial_send_does_not_resend():
    telegram = FakeTelegram(fail={2: TransientError("502")})
    handler = notifier(telegram)
    with pytest.raises(TransientError):
        handler([alert()])

    handler([alert()])  # BatchConsumer 整批重試

    assert [c for c, _ in telegram.sent] == [1, 2]

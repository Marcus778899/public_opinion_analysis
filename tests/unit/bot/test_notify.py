import uuid
from datetime import UTC, datetime, timedelta

import pytest

from radar.bot.notify import AlertNotifier, SentAlerts, fetch_titles, format_alert, post_url
from radar.bot.telegram import TelegramBadRequestError, TelegramForbiddenError
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
        self.fail = fail or {}

    def send_message(self, chat_id, text):
        if chat_id in self.fail:
            raise self.fail.pop(chat_id)
        self.sent.append((chat_id, text))


def notifier(telegram, chats=(1, 2), forgotten=None):
    forgotten = forgotten if forgotten is not None else []
    return AlertNotifier(
        telegram,
        chats_for_board=lambda _board: list(chats),
        titles=lambda ids: {i: f"title of {i}" for i in ids},
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


# --- post_url / format_alert / fetch_titles ---


def test_post_url_builds_ptt_link():
    assert post_url(PID) == "https://www.ptt.cc/bbs/Stock/M.1792000000.A.ABC.html"


def test_format_alert_post_has_title_and_link():
    text = format_alert(alert(), {PID: "[標的] 台積電"})

    assert text.startswith("🔥 [Stock] 文章推文暴增")
    assert "10 分鐘內 45 則推文（平常約 3.2，z=8.0）" in text
    assert "[標的] 台積電\nhttps://www.ptt.cc/bbs/Stock/M.1792000000.A.ABC.html" in text


def test_format_alert_board_lists_sample_posts():
    text = format_alert(alert("board", (PID, PID2)), {PID: "A", PID2: "B"})

    assert text.startswith("📈 [Stock] 看板推文量暴增")
    assert text.index("A\n") < text.index("B\n")


def test_format_alert_missing_title_falls_back_to_post_id():
    assert f"{PID}\nhttps://" in format_alert(alert(), {})


class FakeClickHouse:
    def __init__(self, rows=()) -> None:
        self.rows = list(rows)
        self.calls: list[dict] = []

    def query_rows(self, sql, params=None):
        self.calls.append(params)
        return self.rows


def test_fetch_titles_empty_list_does_not_query():
    ch = FakeClickHouse()

    assert fetch_titles(ch, []) == {}  # type: ignore[arg-type]
    assert ch.calls == []


def test_fetch_titles_passes_array_literal_and_skips_blank_titles():
    ch = FakeClickHouse([{"post_id": PID, "title": "t"}, {"post_id": PID2, "title": ""}])

    assert fetch_titles(ch, [PID, PID2]) == {PID: "t"}  # type: ignore[arg-type]
    assert ch.calls == [{"post_ids": f"['{PID}','{PID2}']"}]


def test_fetch_titles_invalid_post_id_rejected():
    with pytest.raises(ValueError):
        fetch_titles(FakeClickHouse(), ["x'] OR 1=1 --"])  # type: ignore[arg-type]


# --- AlertNotifier ---


def test_notifier_sends_to_every_subscribed_chat():
    telegram = FakeTelegram()

    notifier(telegram)([alert()])

    assert [c for c, _ in telegram.sent] == [1, 2]


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

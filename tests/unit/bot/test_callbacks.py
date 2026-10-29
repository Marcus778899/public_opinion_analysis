from datetime import UTC, datetime

from radar.bot.callbacks import handle_callback, timed
from radar.bot.stats import BoardOverview, PostStats
from radar.bot.views import Action, Callback, ChatPrefs

CHAT = 42
PID = "Stock.M.1792000000.A.ABC"
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)


class FakeSubs:
    def __init__(self, enabled=("Gossiping", "Stock"), subscribed=()) -> None:
        self.enabled = list(enabled)
        self.mine = set(subscribed)

    def enabled_boards(self):
        return sorted(self.enabled)

    def boards_of(self, chat_id):
        return sorted(self.mine)

    def subscribe(self, chat_id, board):
        new = board not in self.mine
        self.mine.add(board)
        return new

    def unsubscribe(self, chat_id, board):
        n = int(board in self.mine)
        self.mine.discard(board)
        return n


class FakePrefs:
    def __init__(self, muted=()) -> None:
        self.current = ChatPrefs()
        self.muted_ids = list(muted)

    def prefs(self, chat_id):
        return self.current

    def toggle(self, chat_id, unit_type):
        if unit_type == "post":
            self.current = ChatPrefs(not self.current.post_alerts, self.current.board_alerts)
        else:
            self.current = ChatPrefs(self.current.post_alerts, not self.current.board_alerts)
        return self.current

    def mute(self, chat_id, post_id):
        new = post_id not in self.muted_ids
        if new:
            self.muted_ids.insert(0, post_id)
        return new

    def unmute(self, chat_id, post_id):
        if post_id in self.muted_ids:
            self.muted_ids.remove(post_id)
            return True
        return False

    def muted(self, chat_id):
        return list(self.muted_ids)


class FakeQueries:
    def __init__(self) -> None:
        self.hot_boards: list[list[str] | None] = []
        self.overviews: list[str] = []

    def post_stats(self, post_ids):
        return {p: PostStats(p, "Stock", f"title {p}", 1, 0, 0, None) for p in post_ids}

    def hot(self, boards):
        self.hot_boards.append(boards)
        return []

    def overview(self, board, now):
        self.overviews.append(board)
        return BoardOverview(board, 0, 0, {}, [], 0)


def run(callback, subs=None, prefs=None, queries=None):
    return handle_callback(
        callback,
        CHAT,
        subs or FakeSubs(),  # type: ignore[arg-type]
        prefs or FakePrefs(),  # type: ignore[arg-type]
        queries or FakeQueries(),
        min_score=0.6,
        now=NOW,
    )


def test_none_callback_shows_expired_menu():
    result = run(None)

    assert result.screen is not None and "過期" in result.screen.text


def test_menu_shows_main_menu():
    assert run(Callback(Action.MENU)).screen is not None


def test_hot_uses_subscribed_boards():
    queries = FakeQueries()

    run(Callback(Action.HOT), FakeSubs(subscribed=["Stock"]), queries=queries)

    assert queries.hot_boards == [["Stock"]]


def test_hot_without_subscriptions_uses_all_boards():
    queries = FakeQueries()

    run(Callback(Action.HOT), queries=queries)

    assert queries.hot_boards == [None]


def test_hot_all_uses_all_boards():
    queries = FakeQueries()

    run(Callback(Action.HOT, "all"), FakeSubs(subscribed=["Stock"]), queries=queries)

    assert queries.hot_boards == [None]


def test_sub_toggles_on_with_toast_and_redraws():
    subs = FakeSubs()

    result = run(Callback(Action.SUB, "Stock"), subs)

    assert subs.mine == {"Stock"}
    assert result.toast == "已訂閱 Stock"
    assert result.screen is not None and "✅ Stock" in str(result.screen.keyboard)


def test_sub_toggles_off_when_already_subscribed():
    subs = FakeSubs(subscribed=["Stock"])

    result = run(Callback(Action.SUB, "Stock"), subs)

    assert subs.mine == set()
    assert result.toast == "已取消 Stock"


def test_sub_disabled_or_unknown_board_rejected():
    subs = FakeSubs()

    result = run(Callback(Action.SUB, "Off"), subs)

    assert subs.mine == set()
    assert result.toast is not None and "找不到" in result.toast


def test_overview_queries_board():
    queries = FakeQueries()

    run(Callback(Action.OVERVIEW, "Stock"), queries=queries)

    assert queries.overviews == ["Stock"]


def test_overview_unknown_board_rejected_without_query():
    queries = FakeQueries()

    result = run(Callback(Action.OVERVIEW, "NoSuch"), queries=queries)

    assert queries.overviews == []
    assert result.toast is not None


def test_toggle_post_alerts():
    prefs = FakePrefs()

    result = run(Callback(Action.TOGGLE, "post"), prefs=prefs)

    assert prefs.current == ChatPrefs(post_alerts=False)
    assert result.toast == "已關閉文章警示"


def test_toggle_unknown_type_rejected():
    prefs = FakePrefs()

    run(Callback(Action.TOGGLE, "entity"), prefs=prefs)

    assert prefs.current == ChatPrefs()


def test_mute_from_alert_only_toasts_without_editing_alert():
    prefs = FakePrefs()

    result = run(Callback(Action.MUTE, PID), prefs=prefs)

    assert prefs.muted_ids == [PID]
    assert (result.screen, result.toast) == (None, "這篇不再通知")


def test_mute_invalid_post_id_rejected():
    prefs = FakePrefs()

    run(Callback(Action.MUTE, "not-a-post"), prefs=prefs)

    assert prefs.muted_ids == []


def test_unmute_redraws_settings_with_titles():
    prefs = FakePrefs(muted=[PID])

    result = run(Callback(Action.UNMUTE, PID), prefs=prefs)

    assert prefs.muted_ids == []
    assert result.toast == "已恢復通知"
    assert result.screen is not None


def test_settings_shows_muted_titles_and_falls_back_to_post_id_on_query_error():
    class BrokenQueries(FakeQueries):
        def post_stats(self, post_ids):
            from radar.common.clickhouse import ClickHouseError

            raise ClickHouseError("down")

    result = run(Callback(Action.SETTINGS), prefs=FakePrefs(muted=[PID]), queries=BrokenQueries())

    assert result.screen is not None and f"1:unmute:{PID}" in str(result.screen.keyboard)


def test_query_error_returns_toast_without_screen():
    class DownQueries(FakeQueries):
        def hot(self, boards):
            from radar.common.clickhouse import ClickHouseError

            raise ClickHouseError("down")

    result = run(Callback(Action.HOT), queries=DownQueries())

    assert (result.screen, result.toast) == (None, "查詢失敗，請稍後再試")


def test_toggle_board_alerts_back_on_says_enabled():
    prefs = FakePrefs()
    run(Callback(Action.TOGGLE, "board"), prefs=prefs)

    assert run(Callback(Action.TOGGLE, "board"), prefs=prefs).toast == "已開啟看板警示"


def test_sub_toggle_answers_after_write_before_requery_and_marks_answered():
    order: list[str] = []

    class Spy(FakeSubs):
        def subscribe(self, chat_id, board):
            order.append("write")
            return super().subscribe(chat_id, board)

        def boards_of(self, chat_id):
            order.append("boards_of")
            return super().boards_of(chat_id)

    result = handle_callback(
        Callback(Action.SUB, "Stock"),
        CHAT,
        Spy(),  # type: ignore[arg-type]
        FakePrefs(),  # type: ignore[arg-type]
        FakeQueries(),
        min_score=0.6,
        now=NOW,
        answer=lambda toast: order.append(f"answer:{toast}"),
    )

    assert order == ["boards_of", "write", "answer:已訂閱 Stock", "boards_of"]
    assert result.answered is True and result.toast == "已訂閱 Stock"


def test_sub_toggle_without_answer_hook_leaves_answered_false():
    result = run(Callback(Action.SUB, "Stock"), FakeSubs())

    assert result.answered is False


def test_sub_toggle_unknown_board_does_not_call_answer():
    called: list[str | None] = []

    handle_callback(
        Callback(Action.SUB, "Off"),
        CHAT,
        FakeSubs(),  # type: ignore[arg-type]
        FakePrefs(),  # type: ignore[arg-type]
        FakeQueries(),
        min_score=0.6,
        now=NOW,
        answer=called.append,
    )

    assert called == []


class _LogSpy:
    def __init__(self) -> None:
        self.lines: list[tuple] = []

    def info(self, *args) -> None:
        self.lines.append(args)


def test_timed_logs_step_name_chat_and_milliseconds(monkeypatch):
    spy = _LogSpy()
    monkeypatch.setattr("radar.bot.callbacks.log", spy)

    with timed("pg_write", 9):
        pass

    fmt, step, chat, ms = spy.lines[0]
    assert (step, chat) == ("pg_write", 9) and ms >= 0 and "ms=" in fmt


def test_timed_logs_even_when_step_raises(monkeypatch):
    spy = _LogSpy()
    monkeypatch.setattr("radar.bot.callbacks.log", spy)

    try:
        with timed("answerCallbackQuery", 9):
            raise ValueError("boom")
    except ValueError:
        pass

    assert spy.lines[0][1] == "answerCallbackQuery"


def test_sub_toggle_logs_every_step(monkeypatch):
    spy = _LogSpy()
    monkeypatch.setattr("radar.bot.callbacks.log", spy)

    handle_callback(
        Callback(Action.SUB, "Stock"),
        CHAT,
        FakeSubs(),  # type: ignore[arg-type]
        FakePrefs(),  # type: ignore[arg-type]
        FakeQueries(),
        min_score=0.6,
        now=NOW,
        answer=lambda toast: None,
    )

    assert [line[1] for line in spy.lines] == [
        "enabled_boards",
        "boards_of",
        "pg_write",
        "answerCallbackQuery",
        "requery_boards_of",
    ]

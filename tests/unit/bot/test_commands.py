import pytest

from radar.bot.commands import COMMANDS, HELP, Command, handle, parse_command, text_reply

CHAT = 42


class FakeRepo:
    def __init__(self, enabled=("Gossiping", "Stock"), subscribed=()) -> None:
        self.enabled = list(enabled)
        self.subs: set[tuple[int, str]] = {(CHAT, b) for b in subscribed}

    def enabled_boards(self):
        return sorted(self.enabled)

    def boards_of(self, chat_id):
        return sorted(b for c, b in self.subs if c == chat_id)

    def subscribe(self, chat_id, board):
        new = (chat_id, board) not in self.subs
        self.subs.add((chat_id, board))
        return new

    def unsubscribe(self, chat_id, board):
        drop = {(c, b) for c, b in self.subs if c == chat_id and (board is None or b == board)}
        self.subs -= drop
        return len(drop)


class FakeQueries:
    def __init__(self, hot=()) -> None:
        self.hot_posts = list(hot)
        self.hot_boards: list[list[str] | None] = []

    def hot(self, boards):
        self.hot_boards.append(boards)
        return self.hot_posts


def run(text: str, repo: FakeRepo | None = None) -> str | None:
    command = parse_command(text)
    assert command is not None
    return text_reply(command, CHAT, repo or FakeRepo())  # type: ignore[arg-type]


def screen(text: str, repo: FakeRepo | None = None, queries: FakeQueries | None = None):
    command = parse_command(text)
    assert command is not None
    return handle(
        command,
        CHAT,
        repo or FakeRepo(),  # type: ignore[arg-type]
        queries or FakeQueries(),  # type: ignore[arg-type]
        min_score=0.6,
    )


# --- parse_command ---


def test_parse_command_with_args():
    assert parse_command("/subscribe Stock") == Command("subscribe", ["Stock"])


def test_parse_command_strips_bot_username():
    assert parse_command("/hot@RadarBot") == Command("hot", [])


def test_parse_command_lowercases_name():
    assert parse_command("/Boards") == Command("boards", [])


@pytest.mark.parametrize("text", ["hello", "", None, "/", "/@bot"])
def test_parse_command_not_a_command_returns_none(text):
    assert parse_command(text) is None


# --- handle（S6-06） ---


def test_start_shows_main_menu_with_buttons():
    assert screen("/start").keyboard


def test_menu_shows_main_menu():
    assert screen("/menu") == screen("/start")


def test_unknown_command_returns_escaped_help():
    reply = screen("/foo")

    assert reply.text.startswith("PTT 輿情雷達")
    assert "&lt;看板&gt;" in reply.text
    assert reply.keyboard == []


def test_hot_command_queries_all_boards():
    queries = FakeQueries()

    screen("/hot", queries=queries)

    assert queries.hot_boards == [None]


def test_text_command_reply_is_escaped():
    reply = screen("/subscribe <b>", FakeRepo(enabled=["<b>"]))

    assert "&lt;b&gt;" in reply.text


def test_commands_list_names_match_handled_commands():
    assert {name for name, _ in COMMANDS} == {"menu", "hot", "boards", "subscribe", "unsubscribe"}


# --- text_reply ---


def test_unknown_command_text_reply_is_none():
    assert run("/foo") is None


def test_help_is_plain_text():
    assert "<看板>" in HELP


def test_boards_lists_enabled_boards_and_marks_subscribed():
    reply = run("/boards", FakeRepo(subscribed=["Stock"]))

    assert "Gossiping\n" in reply
    assert "Stock（已訂閱）" in reply


def test_boards_none_enabled():
    assert run("/boards", FakeRepo(enabled=[])) == "目前沒有可訂閱的看板"


def test_subscribe_enabled_board_succeeds():
    repo = FakeRepo()

    assert "已訂閱 Stock" in run("/subscribe Stock", repo)
    assert repo.subs == {(CHAT, "Stock")}


def test_subscribe_matches_board_case_insensitively():
    repo = FakeRepo()

    run("/subscribe gossiping", repo)

    assert repo.subs == {(CHAT, "Gossiping")}


def test_subscribe_unknown_board_rejected():
    repo = FakeRepo()

    assert "找不到看板" in run("/subscribe NoSuch", repo)
    assert repo.subs == set()


def test_subscribe_without_board_shows_usage():
    assert run("/subscribe").startswith("用法")


def test_subscribe_twice_reports_already_subscribed():
    repo = FakeRepo(subscribed=["Stock"])

    assert "已經訂閱過 Stock" in run("/subscribe Stock", repo)


def test_unsubscribe_board():
    repo = FakeRepo(subscribed=["Stock", "Gossiping"])

    assert run("/unsubscribe stock", repo) == "已取消訂閱 Stock"
    assert repo.subs == {(CHAT, "Gossiping")}


def test_unsubscribe_board_not_subscribed():
    assert "你沒有訂閱 Stock" in run("/unsubscribe Stock")


def test_unsubscribe_without_args_removes_all():
    repo = FakeRepo(subscribed=["Stock", "Gossiping"])

    assert run("/unsubscribe", repo) == "已取消全部 2 個訂閱"
    assert repo.subs == set()


def test_unsubscribe_without_args_when_nothing_subscribed():
    assert run("/unsubscribe") == "你目前沒有訂閱"


def test_hot_command_query_error_says_failed():
    class DownQueries(FakeQueries):
        def hot(self, boards):
            from radar.common.clickhouse import ClickHouseError

            raise ClickHouseError("down")

    assert screen("/hot", queries=DownQueries()).text == "查詢失敗，請稍後再試"

import pytest

from radar.bot.commands import HELP, Command, HotPost, fetch_hot, format_hot, handle, parse_command

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


def run(text: str, repo: FakeRepo | None = None, hot=lambda: []) -> str:
    command = parse_command(text)
    assert command is not None
    return handle(command, CHAT, repo or FakeRepo(), hot)  # type: ignore[arg-type]


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


# --- handle ---


def test_start_returns_help():
    assert run("/start") == HELP


def test_unknown_command_returns_help():
    assert run("/foo") == HELP


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


def test_hot_formats_posts():
    posts = [HotPost("Stock.M.1.A.111", "[標的] 台積電", 50)]

    assert run("/hot", hot=lambda: posts) == "最近 1 小時推文最多：\n1. [標的] 台積電（50 則）"


# --- format_hot / fetch_hot ---


def test_format_hot_empty_says_no_comments():
    assert format_hot([]) == "最近沒有推文"


def test_format_hot_missing_title_uses_post_id():
    assert "Stock.M.1.A.111（3 則）" in format_hot([HotPost("Stock.M.1.A.111", None, 3)])


class FakeClickHouse:
    def __init__(self, rows) -> None:
        self.rows = rows
        self.params = None

    def query_rows(self, sql, params=None):
        self.params = params
        return self.rows


def test_fetch_hot_passes_params_and_maps_rows():
    ch = FakeClickHouse([{"post_id": "Stock.M.1.A.111", "title": "", "comments": "9"}])

    posts = fetch_hot(ch, 60, 5)  # type: ignore[arg-type]

    assert ch.params == {"window_min": "60", "limit": "5"}
    assert posts == [HotPost("Stock.M.1.A.111", None, 9)]

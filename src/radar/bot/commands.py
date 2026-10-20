"""指令解析與回覆（開發規格 7.21、7.23）；查詢 PG、ClickHouse 的部分以參數注入，方便測試。"""

from dataclasses import dataclass

from radar.bot.repository import SubscriptionRepository
from radar.bot.stats import QUERY_ERRORS, Queries
from radar.bot.views import QUERY_FAILED, Screen, escape, hot_screen, main_menu
from radar.common.log import log

# NOTE: 純文字；送出前由 handle 統一 escape（訊息是 HTML，<看板> 會被當成標籤）
HELP = (
    "PTT 輿情雷達：看板推文暴增時通知你。\n"
    "/menu 按鈕選單\n"
    "/boards 可訂閱的看板\n"
    "/subscribe <看板> 訂閱\n"
    "/unsubscribe [看板] 取消訂閱（不帶看板則全部取消）\n"
    "/hot 最近 1 小時推文最多的文章"
)

# setMyCommands 註冊的清單（S6-06）
COMMANDS = [
    ("menu", "按鈕選單"),
    ("hot", "最近 1 小時推文最多的文章"),
    ("boards", "可訂閱的看板"),
    ("subscribe", "訂閱看板，例如 /subscribe Stock"),
    ("unsubscribe", "取消訂閱（不帶看板則全部取消）"),
]


@dataclass(frozen=True)
class Command:
    name: str
    args: list[str]


def parse_command(text: str | None) -> Command | None:
    """ "/subscribe@MyBot Stock" → Command("subscribe", ["Stock"])；不是指令回傳 None。"""
    if not text or not text.startswith("/"):
        return None
    head, *args = text.split()
    name = head[1:].split("@", 1)[0].lower()
    return Command(name, args) if name else None


def handle(
    command: Command,
    chat_id: int,
    repo: SubscriptionRepository,
    queries: Queries,
    *,
    min_score: float,
) -> Screen:
    """/start、/menu → 主選單；/hot → 現在熱門（全部看板）；其他指令 → text_reply 的文字。"""
    if command.name in ("start", "menu"):
        return main_menu()
    if command.name == "hot":
        try:
            posts = queries.hot(None)
        except QUERY_ERRORS as e:
            log.warning("hot query failed: %s", e)
            return Screen(QUERY_FAILED)
        return hot_screen(posts, all_boards=True, min_score=min_score)
    text = text_reply(command, chat_id, repo)
    return Screen(escape(HELP if text is None else text))


def text_reply(command: Command, chat_id: int, repo: SubscriptionRepository) -> str | None:
    """S5-07 的文字指令（純文字）；不是這些指令回傳 None。看板名稱不分大小寫，存成正式寫法。"""
    if command.name == "boards":
        boards = repo.enabled_boards()
        mine = set(repo.boards_of(chat_id))
        lines = [f"{b}{'（已訂閱）' if b in mine else ''}" for b in boards]
        return "可訂閱的看板：\n" + "\n".join(lines) if lines else "目前沒有可訂閱的看板"
    if command.name == "subscribe":
        if len(command.args) != 1:
            return "用法：/subscribe <看板>，例如 /subscribe Stock"
        board = _match_board(command.args[0], repo.enabled_boards())
        if board is None:
            return f"找不到看板 {command.args[0]}，可用 /boards 查看"
        if repo.subscribe(chat_id, board):
            return f"已訂閱 {board}，推文暴增時會通知你"
        return f"你已經訂閱過 {board}"
    if command.name == "unsubscribe":
        if not command.args:
            n = repo.unsubscribe(chat_id, None)
            return f"已取消全部 {n} 個訂閱" if n else "你目前沒有訂閱"
        board = _match_board(command.args[0], repo.boards_of(chat_id))
        if board is None or repo.unsubscribe(chat_id, board) == 0:
            return f"你沒有訂閱 {command.args[0]}"
        return f"已取消訂閱 {board}"
    return None


def _match_board(name: str, boards: list[str]) -> str | None:
    lowered = name.lower()
    return next((b for b in boards if b.lower() == lowered), None)

"""指令解析與回覆文字（開發規格 7.21）；查詢 PG、ClickHouse 的部分以參數注入，方便測試。"""

from collections.abc import Callable
from dataclasses import dataclass

from radar.bot.repository import SubscriptionRepository
from radar.common.clickhouse import ClickHouseClient

HELP = (
    "PTT 輿情雷達：看板推文暴增時通知你。\n"
    "/boards 可訂閱的看板\n"
    "/subscribe <看板> 訂閱\n"
    "/unsubscribe [看板] 取消訂閱（不帶看板則全部取消）\n"
    "/hot 最近 1 小時推文最多的文章"
)

HOT_QUERY = """
SELECT c.post_id AS post_id, count() AS comments, any(p.title) AS title
FROM comments_latest AS c FINAL
LEFT JOIN (SELECT post_id, title FROM posts_latest FINAL) AS p ON p.post_id = c.post_id
WHERE c.is_deleted = 0 AND c.commented_at >= now() - INTERVAL {window_min:UInt32} MINUTE
GROUP BY c.post_id
ORDER BY comments DESC, post_id
LIMIT {limit:UInt32}
"""


@dataclass(frozen=True)
class Command:
    name: str
    args: list[str]


@dataclass(frozen=True)
class HotPost:
    post_id: str
    title: str | None
    comments: int


def parse_command(text: str | None) -> Command | None:
    """ "/subscribe@MyBot Stock" → Command("subscribe", ["Stock"])；不是指令回傳 None。"""
    if not text or not text.startswith("/"):
        return None
    head, *args = text.split()
    name = head[1:].split("@", 1)[0].lower()
    return Command(name, args) if name else None


def fetch_hot(client: ClickHouseClient, window_min: int, limit: int) -> list[HotPost]:
    rows = client.query_rows(HOT_QUERY, {"window_min": str(window_min), "limit": str(limit)})
    return [HotPost(str(r["post_id"]), r["title"] or None, int(r["comments"])) for r in rows]


def handle(
    command: Command,
    chat_id: int,
    repo: SubscriptionRepository,
    hot: Callable[[], list[HotPost]],
) -> str:
    """回傳要回覆的文字；未知指令回覆 HELP。看板名稱比對不分大小寫，存成 PTT 的正式寫法。"""
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
    if command.name == "hot":
        return format_hot(hot())
    return HELP


def _match_board(name: str, boards: list[str]) -> str | None:
    lowered = name.lower()
    return next((b for b in boards if b.lower() == lowered), None)


def format_hot(posts: list[HotPost]) -> str:
    if not posts:
        return "最近沒有推文"
    lines = [f"{i}. {p.title or p.post_id}（{p.comments} 則）" for i, p in enumerate(posts, 1)]
    return "最近 1 小時推文最多：\n" + "\n".join(lines)

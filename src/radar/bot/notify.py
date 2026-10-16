"""消費 alerts、依訂閱推送（開發規格 7.21）；BatchConsumer 的 handler。"""

from collections import OrderedDict
from collections.abc import Callable

from radar.bot.telegram import TelegramBadRequestError, TelegramClient, TelegramForbiddenError
from radar.common.clickhouse import ClickHouseClient
from radar.common.ids import PTT_BASE_URL, split_post_id
from radar.common.log import log
from radar.common.schemas import Alert

TITLES_QUERY = """
SELECT post_id, title FROM posts_latest FINAL WHERE post_id IN {post_ids:Array(String)}
"""


class SentAlerts:
    """已推送的 alert_id（LRU）；同一個警示重送時不重複推送。"""

    def __init__(self, max_size: int = 10_000) -> None:
        self._max_size = max_size
        self._data: OrderedDict[str, None] = OrderedDict()

    def seen(self, alert_id: str) -> bool:
        return alert_id in self._data

    def add(self, alert_id: str) -> None:
        self._data[alert_id] = None
        self._data.move_to_end(alert_id)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)


def post_url(post_id: str) -> str:
    """Gossiping.M.1.A.ABC → https://www.ptt.cc/bbs/Gossiping/M.1.A.ABC.html。"""
    board, filename = split_post_id(post_id)
    return f"{PTT_BASE_URL}/bbs/{board}/{filename}.html"


def fetch_titles(client: ClickHouseClient, post_ids: list[str]) -> dict[str, str]:
    if not post_ids:
        return {}
    # NOTE: Array 參數以 ClickHouse 的字面值格式傳入；post_id 先驗證過，不含引號
    for post_id in post_ids:
        split_post_id(post_id)
    literal = "[" + ",".join(f"'{p}'" for p in post_ids) + "]"
    rows = client.query_rows(TITLES_QUERY, {"post_ids": literal})
    return {str(r["post_id"]): str(r["title"]) for r in rows if r["title"]}


def format_alert(alert: Alert, titles: dict[str, str]) -> str:
    """純文字；文章警示列出該篇，看板警示列出 sample_post_ids 的標題與連結。"""
    stats = f"10 分鐘內 {alert.value} 則推文（平常約 {alert.baseline:.1f}，z={alert.zscore:.1f}）"
    if alert.unit_type == "post":
        head = f"🔥 [{alert.board}] 文章推文暴增\n{stats}"
    else:
        head = f"📈 [{alert.board}] 看板推文量暴增\n{stats}\n熱門文章："
    posts = [f"{titles.get(p, p)}\n{post_url(p)}" for p in alert.sample_post_ids]
    return "\n".join([head, *posts])


class AlertNotifier:
    """handler：去重 → 找訂閱該看板的 chat → 推送；全部送完才回傳（之後才 commit）。"""

    def __init__(
        self,
        telegram: TelegramClient,
        chats_for_board: Callable[[str], list[int]],
        titles: Callable[[list[str]], dict[str, str]],
        forget_chat: Callable[[int], None],
        sent: SentAlerts | None = None,
    ) -> None:
        self._telegram = telegram
        self._chats_for_board = chats_for_board
        self._titles = titles
        self._forget_chat = forget_chat
        self._sent = sent or SentAlerts()
        # (alert_id, chat_id)：整批重試時，已送到的 chat 不重送
        self._delivered = SentAlerts()

    def __call__(self, alerts: list[Alert]) -> None:
        # NOTE: TransientError 不攔，整批重試；已推送的 alert 靠 SentAlerts 不重送
        for alert in alerts:
            alert_id = str(alert.alert_id)
            if self._sent.seen(alert_id):
                continue
            chats = self._chats_for_board(alert.board)
            if chats:
                text = format_alert(alert, self._titles(alert.sample_post_ids))
                for chat_id in chats:
                    self._deliver(alert_id, chat_id, text)
                log.info(
                    "alert %s (%s %s) sent to %d chats",
                    alert_id,
                    alert.unit_type,
                    alert.unit_key,
                    len(chats),
                )
            self._sent.add(alert_id)

    def _deliver(self, alert_id: str, chat_id: int, text: str) -> None:
        key = f"{alert_id}:{chat_id}"
        if self._delivered.seen(key):
            return
        try:
            self._telegram.send_message(chat_id, text)
        except TelegramForbiddenError:
            log.warning("chat %s blocked the bot, removing its subscriptions", chat_id)
            self._forget_chat(chat_id)
        except TelegramBadRequestError as e:
            log.warning("alert %s to chat %s rejected: %s", alert_id, chat_id, e)
        self._delivered.add(key)

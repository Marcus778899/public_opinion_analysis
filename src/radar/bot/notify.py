"""消費 alerts、依訂閱與通知設定推送（開發規格 7.21、7.23）；BatchConsumer 的 handler。"""

from collections import OrderedDict
from collections.abc import Callable

from radar.bot.stats import QUERY_ERRORS, PostStats
from radar.bot.telegram import TelegramBadRequestError, TelegramClient, TelegramForbiddenError
from radar.bot.views import ALERT_TOP_POSTS, Screen
from radar.common.log import log
from radar.common.schemas import Alert


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


def stats_post_ids(alert: Alert) -> list[str]:
    """要查推噓與情緒的文章：文章警示是該篇，看板警示是 sample_post_ids 的前 3 篇。"""
    if alert.unit_type == "post":
        return [alert.unit_key]
    return alert.sample_post_ids[:ALERT_TOP_POSTS]


def safe_stats(
    post_stats: Callable[[list[str]], dict[str, PostStats]], post_ids: list[str]
) -> dict[str, PostStats]:
    """ClickHouse 查詢失敗（QUERY_ERRORS）記 WARNING 回傳空 dict，警示照樣推送。"""
    try:
        return post_stats(post_ids)
    except QUERY_ERRORS as e:
        log.warning("post stats query failed, sending basic alert: %s", e)
        return {}


class AlertNotifier:
    """handler：去重 → 找要通知的 chat（recipients）→ 推送；全部送完才回傳（之後才 commit）。"""

    def __init__(
        self,
        telegram: TelegramClient,
        recipients: Callable[[Alert], list[int]],
        render: Callable[[Alert], Screen],
        forget_chat: Callable[[int], None],
        sent: SentAlerts | None = None,
    ) -> None:
        self._telegram = telegram
        self._recipients = recipients
        self._render = render
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
            chats = self._recipients(alert)
            if chats:
                screen = self._render(alert)
                for chat_id in chats:
                    self._deliver(alert_id, chat_id, screen)
                log.info(
                    "alert %s (%s %s) sent to %d chats",
                    alert_id,
                    alert.unit_type,
                    alert.unit_key,
                    len(chats),
                )
            self._sent.add(alert_id)

    def _deliver(self, alert_id: str, chat_id: int, screen: Screen) -> None:
        key = f"{alert_id}:{chat_id}"
        if self._delivered.seen(key):
            return
        try:
            self._telegram.send_message(chat_id, screen.text, screen.keyboard)
        except TelegramForbiddenError:
            log.warning("chat %s blocked the bot, removing its subscriptions", chat_id)
            self._forget_chat(chat_id)
        except TelegramBadRequestError as e:
            log.warning("alert %s to chat %s rejected: %s", alert_id, chat_id, e)
        self._delivered.add(key)

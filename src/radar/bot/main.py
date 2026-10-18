"""[常駐] Telegram bot（S5-07，設計文件 9.2）：long polling 處理指令，並消費 alerts 推送。

alerts consumer 在 main thread（收 SIGTERM），指令迴圈在另一個 thread；
任一個中止就讓整個服務停止、由 docker 重啟。
"""

import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from radar.bot.callbacks import CallbackResult, handle_callback
from radar.bot.commands import COMMANDS, handle, parse_command
from radar.bot.notify import AlertNotifier, safe_stats, stats_post_ids
from radar.bot.repository import PreferenceRepository, SubscriptionRepository
from radar.bot.stats import ClickHouseQueries, Queries
from radar.bot.telegram import (
    CallbackQuery,
    IncomingMessage,
    TelegramBadRequestError,
    TelegramClient,
    Update,
)
from radar.bot.views import Screen, alert_screen, parse_callback
from radar.common.clickhouse import ClickHouseClient
from radar.common.db.session import make_engine, make_session_factory
from radar.common.kafka import names
from radar.common.kafka.consumer import BatchConsumer, TransientError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.retry import backoff_delays
from radar.common.schemas import Alert
from radar.common.settings import (
    ClickHouseSettings,
    TelegramSettings,
    get_kafka_settings,
    get_postgres_settings,
)

GROUP_ID = "bot"
# 「不再通知」的清理頻率；表很小，每小時一次就夠
PURGE_INTERVAL = timedelta(hours=1)


def is_allowed(chat_id: int | None, allowed: list[int]) -> bool:
    """allowed 為空代表不限制。"""
    if chat_id is None:
        return False
    return not allowed or chat_id in allowed


def reply_to(
    message: IncomingMessage,
    sessions: sessionmaker[Session],
    queries: Queries,
    min_score: float,
) -> Screen | None:
    """一則訊息的回覆；不是指令回傳 None。"""
    command = parse_command(message.text)
    if command is None or message.chat_id is None:
        return None
    with sessions() as session:
        repo = SubscriptionRepository(session)
        return handle(command, message.chat_id, repo, queries, min_score=min_score)


def on_callback(
    callback: CallbackQuery,
    sessions: sessionmaker[Session],
    queries: Queries,
    min_score: float,
    now: datetime,
) -> CallbackResult:
    """parse_callback → callbacks.handle_callback；callback.chat_id 已由呼叫端檢查過。"""
    assert callback.chat_id is not None
    with sessions() as session:
        return handle_callback(
            parse_callback(callback.data),
            callback.chat_id,
            SubscriptionRepository(session),
            PreferenceRepository(session),
            queries,
            min_score=min_score,
            now=now,
        )


def handle_update(
    update: Update,
    telegram: TelegramClient,
    settings: TelegramSettings,
    sessions: sessionmaker[Session],
    queries: Queries,
    now: datetime,
) -> None:
    """允許清單外的 chat 不回應（按鈕回呼也不 answer）。

    訊息 → send_message；按鈕 → 先 answerCallbackQuery（帶 toast），有畫面再 editMessageText。
    """
    allowed = settings.allowed_chat_ids
    min_score = settings.sentiment_min_score
    if update.message is not None:
        message = update.message
        if message.chat_id is None or not is_allowed(message.chat_id, allowed):
            return
        screen = reply_to(message, sessions, queries, min_score)
        if screen is not None:
            _send_reply(telegram, message.chat_id, screen)
        return
    callback = update.callback
    if callback is None or not is_allowed(callback.chat_id, allowed):
        return
    result = on_callback(callback, sessions, queries, min_score, now)
    try:
        telegram.answer_callback_query(callback.id, result.toast)
        if result.screen is not None and callback.chat_id is not None and callback.message_id:
            telegram.edit_message_text(
                callback.chat_id, callback.message_id, result.screen.text, result.screen.keyboard
            )
    except TelegramBadRequestError as e:
        # 例如按鈕回呼超過 Telegram 的期限、原訊息已刪除
        log.warning("callback %s from chat %s rejected: %s", callback.data, callback.chat_id, e)


def purge_muted(sessions: sessionmaker[Session], settings: TelegramSettings, now: datetime) -> int:
    """刪掉超過 mute_retention_h 的「不再通知」。"""
    with sessions() as session:
        deleted = PreferenceRepository(session).purge_muted(
            now - timedelta(hours=settings.mute_retention_h)
        )
    if deleted:
        log.info("purged %d muted posts", deleted)
    return deleted


def register_commands(telegram: TelegramClient) -> None:
    """setMyCommands；失敗只記 WARNING，不擋啟動（指令清單只影響輸入 / 時的提示）。"""
    try:
        telegram.set_my_commands(COMMANDS)
    except (TransientError, TelegramBadRequestError) as e:
        log.warning("setMyCommands failed: %s", e)


def poll_commands(
    telegram: TelegramClient,
    settings: TelegramSettings,
    sessions: sessionmaker[Session],
    queries: Queries,
    stop: threading.Event,
    wait: Callable[[float], bool] | None = None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> None:
    """getUpdates 迴圈：處理完才把 offset 往前推；每 PURGE_INTERVAL 清一次「不再通知」。"""
    wait = wait or stop.wait
    offset: int | None = None
    delays: Iterator[float] = backoff_delays()
    last_purge: datetime | None = None
    while not stop.is_set():
        now = clock()
        if last_purge is None or now - last_purge >= PURGE_INTERVAL:
            purge_muted(sessions, settings, now)
            last_purge = now
        try:
            updates = telegram.get_updates(offset, settings.poll_timeout_s)
            for update in updates:
                handle_update(update, telegram, settings, sessions, queries, now)
                offset = update.update_id + 1
            delays = backoff_delays()
        except TransientError as e:
            delay = e.retry_after_s if e.retry_after_s is not None else next(delays)
            log.warning("telegram polling failed, retry in %.1fs: %s", delay, e)
            wait(delay)


def _send_reply(telegram: TelegramClient, chat_id: int, screen: Screen) -> None:
    try:
        telegram.send_message(chat_id, screen.text, screen.keyboard)
    except TelegramBadRequestError as e:
        log.warning("reply to chat %s rejected: %s", chat_id, e)


class _CommandThread(threading.Thread):
    """包住 poll_commands：結束（包含例外）時通知 consumer 停止，main thread 再把例外拋出。"""

    def __init__(self, target: Callable[[], None], on_exit: Callable[[], None]) -> None:
        super().__init__(name="telegram-commands", daemon=True)
        self._target_fn = target
        self._on_exit = on_exit
        self.error: BaseException | None = None

    def run(self) -> None:
        try:
            self._target_fn()
        except BaseException as e:  # noqa: BLE001 — 交給 main thread 拋出
            self.error = e
        finally:
            self._on_exit()


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("bot")
    settings = TelegramSettings()
    engine = make_engine(get_postgres_settings(), pool_size=2)
    sessions = make_session_factory(engine)
    ch = ClickHouseClient(ClickHouseSettings())
    telegram = TelegramClient(settings)
    producer = JsonProducer(get_kafka_settings())

    queries = ClickHouseQueries(
        ch, hot_window_min=settings.hot_window_min, hot_limit=settings.hot_limit
    )

    def recipients(alert: Alert) -> list[int]:
        with sessions() as session:
            return PreferenceRepository(session).recipients(alert)

    def render(alert: Alert) -> Screen:
        stats = safe_stats(queries.post_stats, stats_post_ids(alert))
        return alert_screen(alert, stats, settings.sentiment_min_score)

    def forget_chat(chat_id: int) -> None:
        with sessions() as session:
            PreferenceRepository(session).forget(chat_id)

    consumer = BatchConsumer(
        get_kafka_settings(),
        group_id=GROUP_ID,
        topics=[names.ALERTS],
        model=Alert,
        handler=AlertNotifier(telegram, recipients, render, forget_chat),
        dlq=DlqPublisher(producer, GROUP_ID),
        batch_size=50,
    )
    stop = threading.Event()
    commands = _CommandThread(
        lambda: poll_commands(telegram, settings, sessions, queries, stop),
        on_exit=consumer.stop,
    )
    register_commands(telegram)
    log.info("bot started; allowed chats: %s", settings.allowed_chat_ids or "all")
    commands.start()
    try:
        consumer.run()
    finally:
        stop.set()
        producer.flush()
        telegram.close()
        ch.close()
        engine.dispose()
    if commands.error is not None:
        raise commands.error


if __name__ == "__main__":
    main()

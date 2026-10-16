"""[常駐] Telegram bot（S5-07，設計文件 9.2）：long polling 處理指令，並消費 alerts 推送。

alerts consumer 在 main thread（收 SIGTERM），指令迴圈在另一個 thread；
任一個中止就讓整個服務停止、由 docker 重啟。
"""

import threading
from collections.abc import Callable, Iterator

from sqlalchemy.orm import Session, sessionmaker

from radar.bot.commands import HotPost, fetch_hot, handle, parse_command
from radar.bot.notify import AlertNotifier, fetch_titles
from radar.bot.repository import SubscriptionRepository
from radar.bot.telegram import IncomingMessage, TelegramBadRequestError, TelegramClient
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


def is_allowed(chat_id: int | None, allowed: list[int]) -> bool:
    """allowed 為空代表不限制。"""
    if chat_id is None:
        return False
    return not allowed or chat_id in allowed


def reply_to(
    message: IncomingMessage,
    sessions: sessionmaker[Session],
    hot: Callable[[], list[HotPost]],
) -> str | None:
    """一則訊息的回覆；不是指令回傳 None。"""
    command = parse_command(message.text)
    if command is None or message.chat_id is None:
        return None
    with sessions() as session:
        return handle(command, message.chat_id, SubscriptionRepository(session), hot)


def poll_commands(
    telegram: TelegramClient,
    settings: TelegramSettings,
    sessions: sessionmaker[Session],
    hot: Callable[[], list[HotPost]],
    stop: threading.Event,
    wait: Callable[[float], bool] | None = None,
) -> None:
    """getUpdates 迴圈：允許清單外的 chat 不回應；處理完才把 offset 往前推。"""
    wait = wait or stop.wait
    offset: int | None = None
    delays: Iterator[float] = backoff_delays()
    while not stop.is_set():
        try:
            updates = telegram.get_updates(offset, settings.poll_timeout_s)
            for message in updates:
                if is_allowed(message.chat_id, settings.allowed_chat_ids):
                    text = reply_to(message, sessions, hot)
                    if text is not None and message.chat_id is not None:
                        _send_reply(telegram, message.chat_id, text)
                offset = message.update_id + 1
            delays = backoff_delays()
        except TransientError as e:
            delay = e.retry_after_s if e.retry_after_s is not None else next(delays)
            log.warning("telegram polling failed, retry in %.1fs: %s", delay, e)
            wait(delay)


def _send_reply(telegram: TelegramClient, chat_id: int, text: str) -> None:
    try:
        telegram.send_message(chat_id, text)
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

    def chats_for_board(board: str) -> list[int]:
        with sessions() as session:
            return SubscriptionRepository(session).chats_for_board(board)

    def forget_chat(chat_id: int) -> None:
        with sessions() as session:
            SubscriptionRepository(session).unsubscribe(chat_id, None)

    consumer = BatchConsumer(
        get_kafka_settings(),
        group_id=GROUP_ID,
        topics=[names.ALERTS],
        model=Alert,
        handler=AlertNotifier(
            telegram, chats_for_board, lambda ids: fetch_titles(ch, ids), forget_chat
        ),
        dlq=DlqPublisher(producer, GROUP_ID),
        batch_size=50,
    )
    stop = threading.Event()
    commands = _CommandThread(
        lambda: poll_commands(
            telegram,
            settings,
            sessions,
            lambda: fetch_hot(ch, settings.hot_window_min, settings.hot_limit),
            stop,
        ),
        on_exit=consumer.stop,
    )
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

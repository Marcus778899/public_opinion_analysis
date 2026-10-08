import signal
import threading
from collections.abc import Callable, Iterator
from types import FrameType

from confluent_kafka import Consumer, KafkaError, KafkaException, Message
from pydantic import BaseModel, ValidationError

from radar.common.kafka.config import consumer_config
from radar.common.kafka.dlq import DlqPublisher
from radar.common.log import log
from radar.common.retry import backoff_delays
from radar.common.settings import KafkaSettings

_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class TransientError(Exception):
    """handler 遇到可重試的錯誤（網路、DB 斷線）時拋出；整批重試、不 commit。"""


class DecodeError(Exception):
    """自訂 decode 遇到壞資料時拋出；與 ValidationError 一樣送 DLQ。"""


class BatchConsumer[T: BaseModel]:
    """at-least-once 的批次 consumer（開發規格 2.2）。

    解析失敗的訊息送 DLQ；handler 拋 TransientError 時退避重試；其他例外直接中止服務。
    """

    def __init__(
        self,
        settings: KafkaSettings,
        *,
        group_id: str,
        topics: list[str],
        model: type[T],
        handler: Callable[[list[T]], None],
        dlq: DlqPublisher,
        batch_size: int = 500,
        batch_timeout_s: float = 1.0,
        consumer: Consumer | None = None,
        backoff: Callable[[], Iterator[float]] = backoff_delays,
        decode: Callable[[Message], T] | None = None,
    ) -> None:
        """decode 預設把訊息當 JSON 驗證成 model；CDC 的 Avro 訊息傳入自訂 decode。"""
        self._consumer = consumer or Consumer(consumer_config(settings, group_id))
        self._consumer.subscribe(topics)
        self._model = model
        self._decode_one = decode or (lambda msg: model.model_validate_json(msg.value() or b""))
        self._handler = handler
        self._dlq = dlq
        self._batch_size = batch_size
        self._batch_timeout_s = batch_timeout_s
        self._backoff = backoff
        self._stop = threading.Event()

    def run(self) -> None:
        """主迴圈，直到 stop() 或收到 SIGTERM / SIGINT。"""
        previous = self._install_signal_handlers()
        try:
            while not self._stop.is_set():
                messages = self._poll_batch()
                if not messages:
                    continue
                items = self._decode(messages)
                if items and not self._handle_with_retry(items):
                    break
                self._consumer.commit(asynchronous=False)
        finally:
            self._consumer.close()
            self._restore_signal_handlers(previous)

    def stop(self) -> None:
        self._stop.set()

    def _poll_batch(self) -> list[Message]:
        messages = self._consumer.consume(self._batch_size, self._batch_timeout_s)
        valid: list[Message] = []
        for msg in messages:
            err = msg.error()
            if err is None:
                valid.append(msg)
            elif err.fatal():
                raise KafkaException(err)
            elif err.code() != KafkaError._PARTITION_EOF:
                log.warning("consumer error (non-fatal): %s", err)
        return valid

    def _decode(self, messages: list[Message]) -> list[T]:
        items: list[T] = []
        for msg in messages:
            try:
                items.append(self._decode_one(msg))
            except (ValidationError, DecodeError) as e:
                self._dlq.publish(msg, e)
        return items

    def _handle_with_retry(self, items: list[T]) -> bool:
        """成功回傳 True；重試期間被要求停止回傳 False（呼叫端不得 commit）。"""
        delays = self._backoff()
        while True:
            try:
                self._handler(items)
                return True
            except TransientError as e:
                if self._stop.is_set():
                    log.warning("stopping during retry, batch left uncommitted: %s", e)
                    return False
                delay = next(delays)
                log.warning("transient error, retry in %.1fs: %s", delay, e)
                self._stop.wait(delay)

    def _install_signal_handlers(self) -> dict[int, object]:
        # NOTE: signal 只能在主執行緒註冊；在其他執行緒跑時由呼叫端負責 stop()
        if threading.current_thread() is not threading.main_thread():
            return {}
        previous: dict[int, object] = {}
        for sig in _STOP_SIGNALS:
            previous[sig] = signal.signal(sig, self._on_signal)
        return previous

    def _restore_signal_handlers(self, previous: dict[int, object]) -> None:
        for sig, handler in previous.items():
            signal.signal(sig, handler)  # type: ignore[arg-type]

    def _on_signal(self, signum: int, frame: FrameType | None) -> None:
        log.info("received signal %s, finishing current batch", signum)
        self.stop()

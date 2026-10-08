import signal
import threading
import time
from collections.abc import Callable, Iterator
from types import FrameType

from confluent_kafka import Consumer, KafkaError, KafkaException, Message, TopicPartition
from pydantic import BaseModel, ValidationError

from radar.common.kafka.config import consumer_config
from radar.common.kafka.dlq import DlqPublisher
from radar.common.log import log
from radar.common.retry import backoff_delays
from radar.common.settings import KafkaSettings

_STOP_SIGNALS = (signal.SIGTERM, signal.SIGINT)


class TransientError(Exception):
    """handler 遇到可重試的錯誤（網路、DB 斷線）時拋出；整批重試、不 commit。

    retry_after_s 有值時以它取代退避秒數（例如 LLM 每日額度的冷卻時間）。
    """

    def __init__(self, message: str, *, retry_after_s: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_s = retry_after_s


# commit 時遇到這些錯誤代表 partition 已被分給別人；該批由新的擁有者重做（開發規格 2.2）
_LOST_ASSIGNMENT_CODES = frozenset(
    {
        KafkaError._ASSIGNMENT_LOST,
        KafkaError.UNKNOWN_MEMBER_ID,
        KafkaError.ILLEGAL_GENERATION,
        KafkaError.REBALANCE_IN_PROGRESS,
    }
)


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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """decode 預設把訊息當 JSON 驗證成 model；CDC 的 Avro 訊息傳入自訂 decode。"""
        self._consumer = consumer or Consumer(consumer_config(settings, group_id))
        self._consumer.subscribe(topics, on_assign=self._on_assign)
        self._model = model
        self._decode_one = decode or (lambda msg: model.model_validate_json(msg.value() or b""))
        self._handler = handler
        self._dlq = dlq
        self._batch_size = batch_size
        self._batch_timeout_s = batch_timeout_s
        self._backoff = backoff
        self._clock = clock
        self._stop = threading.Event()
        self._retrying = False

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
                self._commit()
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
        paused = False
        try:
            while True:
                try:
                    self._handler(items)
                    return True
                except TransientError as e:
                    if self._stop.is_set():
                        log.warning("stopping during retry, batch left uncommitted: %s", e)
                        return False
                    if not paused:
                        self._pause_assigned()
                        paused = True
                    delay = e.retry_after_s if e.retry_after_s is not None else next(delays)
                    log.warning("transient error, retry in %.1fs: %s", delay, e)
                    self._wait_keeping_membership(delay)
                    if self._stop.is_set():
                        log.warning("stopping during retry, batch left uncommitted: %s", e)
                        return False
        finally:
            if paused:
                self._resume_assigned()

    def _wait_keeping_membership(self, delay_s: float) -> None:
        """等待 delay_s 秒，期間持續 poll() 讓 broker 知道成員還活著。"""
        deadline = self._clock() + delay_s
        while not self._stop.is_set():
            remaining = deadline - self._clock()
            if remaining <= 0:
                return
            msg = self._consumer.poll(min(remaining, 1.0))
            if msg is not None:
                self._seek_back(msg)

    def _seek_back(self, msg: Message) -> None:
        """把重試期間意外收到的訊息倒回去，resume 後重新收到。"""
        err = msg.error()
        if err is not None:
            if err.fatal():
                raise KafkaException(err)
            return
        log.warning(
            "message received while paused, seeking back topic=%s partition=%s offset=%s",
            msg.topic(),
            msg.partition(),
            msg.offset(),
        )
        self._consumer.seek(TopicPartition(msg.topic(), msg.partition(), msg.offset()))

    def _pause_assigned(self) -> None:
        self._retrying = True
        partitions = self._consumer.assignment()
        if partitions:
            self._consumer.pause(partitions)

    def _resume_assigned(self) -> None:
        self._retrying = False
        partitions = self._consumer.assignment()
        if partitions:
            self._consumer.resume(partitions)

    def _on_assign(self, consumer: Consumer, partitions: list[TopicPartition]) -> None:
        """rebalance 分到新 partition 時的 callback；重試中要一併 pause，否則會收到新訊息。"""
        if not self._retrying:
            return  # 由 client 在 callback 返回後自動 assign
        # NOTE: 先 assign 才能 pause；callback 內自行 assign 時 client 不會再 assign 一次
        consumer.assign(partitions)
        consumer.pause(partitions)

    def _commit(self) -> None:
        """同步 commit；失去 assignment 只記 warning（開發規格 2.2），其他錯誤照舊拋出。"""
        try:
            self._consumer.commit(asynchronous=False)
        except KafkaException as e:
            err = e.args[0] if e.args else None
            if err is None or err.code() not in _LOST_ASSIGNMENT_CODES:
                raise
            log.warning("commit skipped, partitions reassigned (batch will be redone): %s", err)

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

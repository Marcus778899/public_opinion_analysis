"""confluent-kafka 的測試替身，只實作 radar.common.kafka 用到的介面。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from confluent_kafka import KafkaError


class FakeError:
    def __init__(self, code: int, *, fatal: bool = False) -> None:
        self._code = code
        self._fatal = fatal

    def code(self) -> int:
        return self._code

    def fatal(self) -> bool:
        return self._fatal

    def __str__(self) -> str:
        return f"FakeError({self._code})"


PARTITION_EOF = FakeError(KafkaError._PARTITION_EOF)


@dataclass
class FakeMessage:
    value_: bytes | None
    key_: bytes | None = b"k"
    topic_: str = "in"
    partition_: int = 0
    offset_: int = 0
    error_: FakeError | None = None

    def value(self) -> bytes | None:
        return self.value_

    def key(self) -> bytes | None:
        return self.key_

    def topic(self) -> str:
        return self.topic_

    def partition(self) -> int:
        return self.partition_

    def offset(self) -> int:
        return self.offset_

    def error(self) -> FakeError | None:
        return self.error_


@dataclass
class FakeProducer:
    fail_delivery: bool = False
    remaining_on_flush: int = 0
    buffer_full_times: int = 0
    produced: list[dict[str, Any]] = field(default_factory=list)
    _pending: list[tuple[Callable[..., None], FakeMessage]] = field(default_factory=list)

    def produce(self, topic: str, key: bytes, value: bytes, on_delivery: Callable) -> None:
        if self.buffer_full_times:
            self.buffer_full_times -= 1
            raise BufferError("queue full")
        self.produced.append({"topic": topic, "key": key, "value": value})
        self._pending.append((on_delivery, FakeMessage(value, key, topic)))

    def poll(self, timeout: float = 0) -> int:
        return 0

    def flush(self, timeout: float = 0) -> int:
        err = FakeError(KafkaError._MSG_TIMED_OUT) if self.fail_delivery else None
        for callback, msg in self._pending:
            callback(err, msg)
        self._pending.clear()
        return self.remaining_on_flush


@dataclass
class FakeConsumer:
    """依序回傳 batches；用完後呼叫 on_exhausted（通常是 BatchConsumer.stop）。"""

    batches: list[list[FakeMessage]]
    on_exhausted: Callable[[], None] | None = None
    subscribed: list[str] = field(default_factory=list)
    commits: int = 0
    closed: bool = False

    def subscribe(self, topics: list[str]) -> None:
        self.subscribed = topics

    def consume(self, num_messages: int, timeout: float) -> list[FakeMessage]:
        if self.batches:
            return self.batches.pop(0)
        if self.on_exhausted:
            self.on_exhausted()
        return []

    def commit(self, asynchronous: bool = True) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True

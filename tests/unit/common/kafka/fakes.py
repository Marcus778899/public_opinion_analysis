"""confluent-kafka 的測試替身，只實作 radar.common.kafka 用到的介面。"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from confluent_kafka import KafkaError, TopicPartition


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
class FakeTopicMetadata:
    partitions: dict[int, object]
    error: FakeError | None = None


@dataclass
class FakeClusterMetadata:
    topics: dict[str, FakeTopicMetadata]


@dataclass
class FakeProducer:
    fail_delivery: bool = False
    remaining_on_flush: int = 0
    buffer_full_times: int = 0
    # list_topics 回傳的 topic → partition 數；不在其中的 topic 視為不存在
    topic_partitions: dict[str, int] = field(default_factory=dict)
    metadata_calls: int = 0
    produced: list[dict[str, Any]] = field(default_factory=list)
    _pending: list[tuple[Callable[..., None], FakeMessage]] = field(default_factory=list)

    def produce(
        self, topic: str, key: bytes, value: bytes, on_delivery: Callable, **kwargs: int
    ) -> None:
        if self.buffer_full_times:
            self.buffer_full_times -= 1
            raise BufferError("queue full")
        self.produced.append({"topic": topic, "key": key, "value": value, **kwargs})
        self._pending.append((on_delivery, FakeMessage(value, key, topic)))

    def list_topics(self, topic: str, timeout: float = -1) -> FakeClusterMetadata:
        self.metadata_calls += 1
        if topic not in self.topic_partitions:
            return FakeClusterMetadata(topics={})
        count = self.topic_partitions[topic]
        return FakeClusterMetadata(
            topics={topic: FakeTopicMetadata(partitions=dict.fromkeys(range(count)))}
        )

    def poll(self, timeout: float = 0) -> int:
        return 0

    def flush(self, timeout: float = 0) -> int:
        err = FakeError(KafkaError._MSG_TIMED_OUT) if self.fail_delivery else None
        for callback, msg in self._pending:
            callback(err, msg)
        self._pending.clear()
        return self.remaining_on_flush


class FakeClock:
    """poll(timeout) 會推進時間，等待不必真的 sleep。"""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


@dataclass
class FakeConsumer:
    """依序回傳 batches；用完後呼叫 on_exhausted（通常是 BatchConsumer.stop）。"""

    batches: list[list[FakeMessage]]
    on_exhausted: Callable[[], None] | None = None
    subscribed: list[str] = field(default_factory=list)
    on_assign: Callable[..., None] | None = None
    commits: int = 0
    commit_errors: list[Exception] = field(default_factory=list)
    closed: bool = False
    assigned: list[TopicPartition] = field(default_factory=lambda: [TopicPartition("in", 0)])
    paused: set[tuple[str, int]] = field(default_factory=set)
    pause_calls: int = 0
    resume_calls: int = 0
    poll_results: list[FakeMessage | None] = field(default_factory=list)
    polls: list[float] = field(default_factory=list)
    seeks: list[tuple[str, int, int]] = field(default_factory=list)
    clock: FakeClock | None = None

    def subscribe(self, topics: list[str], on_assign: Callable[..., None] | None = None) -> None:
        self.subscribed = topics
        self.on_assign = on_assign

    def consume(self, num_messages: int, timeout: float) -> list[FakeMessage]:
        if self.batches:
            return self.batches.pop(0)
        if self.on_exhausted:
            self.on_exhausted()
        return []

    def poll(self, timeout: float = -1) -> FakeMessage | None:
        self.polls.append(timeout)
        if self.clock is not None:
            self.clock.t += timeout
        return self.poll_results.pop(0) if self.poll_results else None

    def assignment(self) -> list[TopicPartition]:
        return list(self.assigned)

    def assign(self, partitions: list[TopicPartition]) -> None:
        self.assigned = list(partitions)

    def pause(self, partitions: list[TopicPartition]) -> None:
        self.pause_calls += 1
        self.paused |= {(p.topic, p.partition) for p in partitions}

    def resume(self, partitions: list[TopicPartition]) -> None:
        self.resume_calls += 1
        self.paused -= {(p.topic, p.partition) for p in partitions}

    def seek(self, partition: TopicPartition) -> None:
        self.seeks.append((partition.topic, partition.partition, partition.offset))

    def commit(self, asynchronous: bool = True) -> None:
        if self.commit_errors:
            raise self.commit_errors.pop(0)
        self.commits += 1

    def close(self) -> None:
        self.closed = True

"""#293 producer-fatal-exit：JsonProducer fatal 後丟 ProducerFatalError，服務結束由 docker 重啟。

約定的對外介面（實作須照此命名，開發規格 7.30 A）：
- radar.common.kafka.producer.ProducerFatalError(Exception)，屬性 error: KafkaError；
  不繼承 KafkaException、DeliveryError
- JsonProducer.fatal_error property；建 Producer 時 config 帶 error_cb
- radar.collector.scheduler._logged(fn, on_fatal)
- radar.api.main.exit_for_restart()：先 log.close() 再 os._exit(70)
"""

import itertools
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from confluent_kafka import KafkaError, KafkaException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from tests.unit.common.kafka.fakes import FakeConsumer, FakeMessage, FakeProducer

from radar.api import main as api_main
from radar.api.deps import get_producer, get_repository
from radar.api.repository import BoardNotFoundError
from radar.api.schemas import BoardOut
from radar.collector import scheduler as scheduler_module
from radar.collector.recrawl import DuePost, DuePostDispatcher
from radar.collector.scheduler import _logged, make_list_task_sender
from radar.common.db.models import Board
from radar.common.kafka import producer as producer_module
from radar.common.kafka.consumer import BatchConsumer
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import DeliveryError, JsonProducer, ProducerFatalError
from radar.common.log import log
from radar.common.settings import ApiSettings, KafkaSettings

SETTINGS = KafkaSettings(bootstrap_servers="unused:9092")
NOW = datetime(2026, 11, 4, 3, 0, tzinfo=UTC)


class Event(BaseModel):
    id: int


def fatal_err() -> KafkaError:
    return KafkaError(KafkaError._FATAL, "idempotent producer inconsistent", fatal=True)


def plain_err() -> KafkaError:
    return KafkaError(KafkaError._MSG_TIMED_OUT, "timed out")


class ScriptedProducer:
    """可指定 produce 丟什麼、delivery callback 回什麼的 confluent Producer 替身。"""

    def __init__(
        self,
        *,
        produce_error: KafkaException | None = None,
        delivery_error: KafkaError | None = None,
        remaining: int = 0,
    ) -> None:
        self.produce_error = produce_error
        self.delivery_error = delivery_error
        self.remaining = remaining
        self.produce_calls = 0
        self.flush_calls = 0
        self._pending: list[Any] = []

    def produce(self, topic, key, value, on_delivery, **kwargs) -> None:
        self.produce_calls += 1
        if self.produce_error is not None:
            raise self.produce_error
        msg = SimpleNamespace(topic=lambda: topic, key=lambda: key)
        self._pending.append((on_delivery, msg))

    def poll(self, timeout: float = 0) -> int:
        return 0

    def flush(self, timeout: float = 0) -> int:
        self.flush_calls += 1
        for callback, msg in self._pending:
            callback(self.delivery_error, msg)
        self._pending.clear()
        return self.remaining

    def list_topics(self, topic, timeout=-1):
        part = SimpleNamespace(partitions={0: None, 1: None, 2: None}, error=None)
        return SimpleNamespace(topics={topic: part})


def fatal_on_produce() -> ScriptedProducer:
    return ScriptedProducer(produce_error=KafkaException(fatal_err()))


def make(fake) -> JsonProducer:
    return JsonProducer(SETTINGS, producer=fake)


def fatal_producer() -> JsonProducer:
    """已進入 fatal 狀態的 JsonProducer。"""
    p = make(fatal_on_produce())
    with pytest.raises(ProducerFatalError):
        p.send("t", "k", Event(id=1))
    return p


# --- 1. 三種 fatal 入口 ---


def test_produce_fatal_kafka_exception_raises_producer_fatal_error():
    p = make(fatal_on_produce())

    with pytest.raises(ProducerFatalError) as info:
        p.send("t", "k", Event(id=1))

    assert info.value.error.fatal()
    assert p.fatal_error is not None


def test_producer_fatal_error_is_not_kafka_exception_nor_delivery_error():
    assert not issubclass(ProducerFatalError, KafkaException)
    assert not issubclass(ProducerFatalError, DeliveryError)
    assert issubclass(ProducerFatalError, Exception)


def test_produce_fatal_error_not_caught_by_existing_except_tuple():
    p = make(fatal_on_produce())

    with pytest.raises(ProducerFatalError):
        try:
            p.send("t", "k", Event(id=1))
        except (DeliveryError, TimeoutError, KafkaException, BufferError):
            pytest.fail("fatal error was swallowed by the existing except tuple")


def test_delivery_callback_fatal_error_raises_on_flush():
    fake = ScriptedProducer(delivery_error=fatal_err())
    p = make(fake)
    p.send("t", "k", Event(id=1))

    with pytest.raises(ProducerFatalError):
        p.flush()

    assert p.fatal_error is not None


def test_delivery_fatal_error_wins_over_timeout_when_messages_remain():
    fake = ScriptedProducer(delivery_error=fatal_err(), remaining=1)
    p = make(fake)
    p.send("t", "k", Event(id=1))

    with pytest.raises(ProducerFatalError):
        p.flush()


def test_delivery_fatal_error_not_wrapped_in_delivery_error():
    fake = ScriptedProducer(delivery_error=fatal_err())
    p = make(fake)
    p.send("t", "k", Event(id=1))

    with pytest.raises(ProducerFatalError) as info:
        p.flush()

    assert not isinstance(info.value, DeliveryError)


class CapturingProducer(ScriptedProducer):
    """取代 confluent Producer 類別，抓出建構時的 config。"""

    last_config: dict[str, Any]

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__()
        type(self).last_config = config


def test_error_cb_registered_in_producer_config(monkeypatch):
    monkeypatch.setattr(producer_module, "Producer", CapturingProducer)

    JsonProducer(SETTINGS)

    assert callable(CapturingProducer.last_config.get("error_cb"))


def test_error_cb_with_fatal_error_makes_send_and_flush_raise(monkeypatch):
    monkeypatch.setattr(producer_module, "Producer", CapturingProducer)
    p = JsonProducer(SETTINGS)

    CapturingProducer.last_config["error_cb"](fatal_err())

    assert p.fatal_error is not None
    with pytest.raises(ProducerFatalError):
        p.send("t", "k", Event(id=1))
    with pytest.raises(ProducerFatalError):
        p.flush()


def test_error_cb_with_non_fatal_error_is_ignored_and_not_logged(monkeypatch):
    monkeypatch.setattr(producer_module, "Producer", CapturingProducer)
    logged: list[str] = []
    for level in ("warning", "error", "critical", "info"):
        monkeypatch.setattr(producer_module.log, level, lambda *a, **k: logged.append(str(a)))
    p = JsonProducer(SETTINGS)

    CapturingProducer.last_config["error_cb"](KafkaError(KafkaError._TRANSPORT, "down"))

    assert p.fatal_error is None
    assert logged == []
    p.send("t", "k", Event(id=1))
    p.flush()


# --- 2. fatal 後的行為 ---


def test_send_after_fatal_raises_without_calling_librdkafka():
    fake = fatal_on_produce()
    p = make(fake)
    with pytest.raises(ProducerFatalError):
        p.send("t", "k", Event(id=1))
    calls = fake.produce_calls

    with pytest.raises(ProducerFatalError):
        p.send("t", "k", Event(id=2))

    assert fake.produce_calls == calls


def test_flush_after_fatal_raises_immediately_without_waiting():
    fake = fatal_on_produce()
    p = make(fake)
    with pytest.raises(ProducerFatalError):
        p.send("t", "k", Event(id=1))

    with pytest.raises(ProducerFatalError):
        p.flush()

    assert fake.flush_calls == 0


def test_fatal_error_keeps_the_first_error():
    p = fatal_producer()
    first = p.fatal_error

    with pytest.raises(ProducerFatalError):
        p.send("t", "k", Event(id=2))

    assert p.fatal_error is first


def test_non_fatal_produce_kafka_exception_still_raises_kafka_exception():
    fake = ScriptedProducer(produce_error=KafkaException(plain_err()))
    p = make(fake)

    with pytest.raises(KafkaException) as info:
        p.send("t", "k", Event(id=1))

    assert not isinstance(info.value, ProducerFatalError)
    assert p.fatal_error is None


def test_non_fatal_delivery_error_still_raises_delivery_error_and_producer_stays_usable():
    fake = ScriptedProducer(delivery_error=plain_err())
    p = make(fake)
    p.send("t", "k", Event(id=1))

    with pytest.raises(DeliveryError):
        p.flush()

    assert p.fatal_error is None
    fake.delivery_error = None
    p.send("t", "k", Event(id=2))
    p.flush()


def test_flush_timeout_without_fatal_still_raises_timeout_error():
    fake = ScriptedProducer(remaining=2)
    p = make(fake)
    p.send("t", "k", Event(id=1))

    with pytest.raises(TimeoutError):
        p.flush()


def test_healthy_producer_send_and_flush_unchanged():
    fake = FakeProducer()
    p = make(fake)

    p.send("t", "k", Event(id=1))
    p.flush()

    assert len(fake.produced) == 1
    assert p.fatal_error is None


# --- 3. scheduler ---


def test_list_task_sender_lets_fatal_error_propagate():
    send = make_list_task_sender(fatal_producer(), lambda: ["Gossiping"])

    with pytest.raises(ProducerFatalError):
        send("Gossiping")


def test_list_task_sender_fatal_at_flush_propagates():
    p = make(ScriptedProducer(delivery_error=fatal_err()))
    send = make_list_task_sender(p, lambda: ["Gossiping"])

    with pytest.raises(ProducerFatalError):
        send("Gossiping")


def test_list_task_sender_non_fatal_kafka_error_is_still_swallowed():
    p = make(ScriptedProducer(produce_error=KafkaException(plain_err())))
    send = make_list_task_sender(p, lambda: ["Gossiping"])

    send("Gossiping")


class FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self) -> None:
        self.committed = True


def test_due_post_dispatcher_lets_fatal_error_propagate_and_does_not_record(monkeypatch):
    due = [DuePost("Gossiping.M.1.A.111", "Gossiping", "https://x/1", NOW)]
    recorded: list[object] = []
    monkeypatch.setattr("radar.collector.recrawl.find_due_posts", lambda *a, **k: due)
    monkeypatch.setattr(
        "radar.collector.recrawl.record_dispatch", lambda *a, **k: recorded.append(1)
    )
    dispatcher = DuePostDispatcher(
        lambda: FakeSession(), fatal_producer(), limit=10, time_scale=1.0
    )

    with pytest.raises(ProducerFatalError):
        dispatcher(NOW)

    assert recorded == []


def test_logged_calls_on_fatal_with_the_error_and_does_not_raise():
    seen: list[ProducerFatalError] = []
    error = ProducerFatalError(fatal_err())

    def job() -> None:
        raise error

    _logged(job, seen.append)()

    assert seen == [error]


def test_logged_still_swallows_ordinary_exceptions_without_on_fatal():
    seen: list[object] = []

    def job() -> None:
        raise RuntimeError("boom")

    _logged(job, seen.append)()

    assert seen == []


def test_logged_passes_through_job_arguments_for_list_tasks():
    calls: list[str] = []

    _logged(lambda board: calls.append(board), lambda e: None)("Gossiping")

    assert calls == ["Gossiping"]


class FakeJob:
    def __init__(self, func, args, job_id) -> None:
        self.func, self.args, self.id = func, list(args or []), job_id

    def remove(self) -> None:
        pass


class FakeScheduler:
    """start() 依序執行每個工作一次（含執行中新增的）；shutdown 後停止。"""

    def __init__(self, *a, **k) -> None:
        self.jobs: list[FakeJob] = []
        self.shutdown_calls: list[dict] = []
        self.stopped = False

    def add_job(self, func, trigger=None, *, id=None, args=None, **kw) -> None:
        self.jobs.append(FakeJob(func, args, id))

    def get_jobs(self) -> list[FakeJob]:
        return list(self.jobs)

    def get_job(self, job_id: str) -> FakeJob | None:
        return next((j for j in self.jobs if j.id == job_id), None)

    def reschedule_job(self, *a, **k) -> None:
        pass

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_calls.append({"wait": wait})
        self.stopped = True

    def start(self) -> None:
        for job in itertools.takewhile(lambda _: not self.stopped, self._iter()):
            job.func(*job.args)

    def _iter(self):
        i = 0
        while i < len(self.jobs):
            yield self.jobs[i]
            i += 1


class FakeLock:
    instances: list["FakeLock"] = []

    def __init__(self, engine) -> None:
        self.released = False
        FakeLock.instances.append(self)

    def wait_until_acquired(self, poll_s=10.0, stop=lambda: False) -> bool:
        return True

    def is_held(self) -> bool:
        return True

    def release(self) -> None:
        self.released = True


class FakeEngine:
    def dispose(self) -> None:
        pass


class FakeBoards:
    def __init__(self, api_url: str) -> None:
        pass

    def fetch(self) -> list[BoardOut]:
        return [
            BoardOut(
                board="Gossiping", enabled=True, interval_sec=60, recrawl_min_push=0, updated_at=NOW
            )
        ]

    def close(self) -> None:
        pass


class WiredScheduler:
    def __init__(self) -> None:
        self.scheduler: FakeScheduler | None = None
        self.emitted: list[tuple[Any, ...]] = []


@pytest.fixture
def wired(monkeypatch) -> WiredScheduler:
    """把 scheduler.main() 的外部依賴換掉；回傳可檢查的狀態。"""
    state = WiredScheduler()
    FakeLock.instances.clear()

    def make_scheduler(*a, **k) -> FakeScheduler:
        state.scheduler = FakeScheduler()
        return state.scheduler

    monkeypatch.setattr(scheduler_module, "setup_logging", lambda name: None)
    monkeypatch.setattr(scheduler_module, "get_postgres_settings", lambda: None)
    monkeypatch.setattr(scheduler_module, "get_kafka_settings", lambda: None)
    monkeypatch.setattr(scheduler_module, "make_engine", lambda *a, **k: FakeEngine())
    monkeypatch.setattr(scheduler_module, "make_session_factory", lambda engine: None)
    monkeypatch.setattr(scheduler_module, "AdvisoryLock", FakeLock)
    monkeypatch.setattr(
        scheduler_module,
        "JsonProducer",
        lambda settings: SimpleNamespace(flush=lambda *a, **k: None),
    )
    monkeypatch.setattr(scheduler_module, "BoardsClient", FakeBoards)
    monkeypatch.setattr(scheduler_module, "BlockingScheduler", make_scheduler)
    monkeypatch.setattr(scheduler_module.signal, "signal", lambda *a, **k: None)
    monkeypatch.setattr(
        type(log), "_emit_failure", lambda self, level, *a, **k: state.emitted.append((level, *a))
    )
    return state


def use_sender(monkeypatch, sender) -> None:
    monkeypatch.setattr(scheduler_module, "make_list_task_sender", lambda *a, **k: sender)


def use_dispatcher(monkeypatch, fn) -> None:
    monkeypatch.setattr(scheduler_module, "DuePostDispatcher", lambda *a, **k: fn)


def raise_fatal(*a, **k) -> None:
    raise ProducerFatalError(fatal_err())


def is_critical(level: object) -> bool:
    return str(level).upper() == "CRITICAL" or level == 50


def test_main_list_task_fatal_stops_scheduler_and_reraises_with_critical(monkeypatch, wired):
    use_sender(monkeypatch, raise_fatal)
    use_dispatcher(monkeypatch, lambda: 0)

    with pytest.raises(ProducerFatalError):
        scheduler_module.main()

    assert wired.scheduler.shutdown_calls == [{"wait": False}]
    assert any(is_critical(e[0]) for e in wired.emitted)


def test_main_due_posts_fatal_stops_scheduler_and_reraises_with_critical(monkeypatch, wired):
    use_sender(monkeypatch, lambda board: None)
    use_dispatcher(monkeypatch, raise_fatal)

    with pytest.raises(ProducerFatalError):
        scheduler_module.main()

    assert wired.scheduler.shutdown_calls == [{"wait": False}]
    assert any(is_critical(e[0]) for e in wired.emitted)


def test_main_fatal_releases_advisory_lock_before_reraising(monkeypatch, wired):
    use_sender(monkeypatch, lambda board: None)
    use_dispatcher(monkeypatch, raise_fatal)

    with pytest.raises(ProducerFatalError):
        scheduler_module.main()

    assert [lock.released for lock in FakeLock.instances] == [True]


def test_main_ordinary_job_error_does_not_stop_scheduler(monkeypatch, wired):
    use_sender(monkeypatch, lambda board: None)
    use_dispatcher(monkeypatch, lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    scheduler_module.main()

    assert wired.scheduler.shutdown_calls == []
    assert not any(is_critical(e[0]) for e in wired.emitted)


# --- 4. BatchConsumer 服務 ---


def msg(event_id: int, offset: int = 0) -> FakeMessage:
    return FakeMessage(json.dumps({"id": event_id}).encode(), offset_=offset)


def build_consumer(batches, handler, dlq_producer: JsonProducer):
    fake = FakeConsumer(batches=batches)
    consumer = BatchConsumer(
        SETTINGS,
        group_id="g",
        topics=["in"],
        model=Event,
        handler=handler,
        dlq=DlqPublisher(dlq_producer, "test"),
        consumer=fake,
        backoff=lambda: itertools.repeat(0),
    )
    fake.on_exhausted = consumer.stop
    return consumer, fake


def test_consumer_handler_fatal_error_aborts_run_without_commit():
    out = fatal_producer()

    def handler(items: list[Event]) -> None:
        for item in items:
            out.send("out", str(item.id), item)

    consumer, fake = build_consumer([[msg(1)]], handler, make(FakeProducer()))

    with pytest.raises(ProducerFatalError):
        consumer.run()

    assert fake.commits == 0
    assert fake.closed


def test_consumer_dlq_fatal_error_aborts_run_without_commit():
    consumer, fake = build_consumer(
        [[FakeMessage(b"not json")]], lambda items: None, fatal_producer()
    )

    with pytest.raises(ProducerFatalError):
        consumer.run()

    assert fake.commits == 0
    assert fake.closed


# --- 5. API ---


class FakeRepo:
    def get(self, board: str) -> Board:
        if board != "Gossiping":
            raise BoardNotFoundError(board)
        return Board(board=board, enabled=True, interval_sec=60, recrawl_min_push=0, updated_at=NOW)

    def list_all(self) -> list[Board]:
        return [self.get("Gossiping")]


@pytest.fixture
def exits(monkeypatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(api_main, "exit_for_restart", lambda: calls.append("exit"))
    return calls


def api_client(producer: JsonProducer) -> TestClient:
    app = api_main.create_app(settings=ApiSettings(cors_origins=[]), use_lifespan=False)
    app.dependency_overrides[get_repository] = lambda: FakeRepo()
    app.dependency_overrides[get_producer] = lambda: producer
    return TestClient(app)


def test_api_fatal_error_returns_503_and_calls_exit_for_restart(exits):
    response = api_client(fatal_producer()).post("/boards/Gossiping/crawl")

    assert response.status_code == 503
    assert response.json() == {"detail": "kafka unavailable"}
    assert exits == ["exit"]


def test_api_fatal_detected_at_flush_also_returns_503_and_exits(exits):
    p = make(ScriptedProducer(delivery_error=fatal_err()))

    response = api_client(p).post("/boards/Gossiping/crawl")

    assert response.status_code == 503
    assert exits == ["exit"]


def test_api_fatal_logs_critical(monkeypatch, exits):
    levels: list[str] = []
    monkeypatch.setattr(
        type(log), "_emit_failure", lambda self, level, *a, **k: levels.append(str(level))
    )
    for name in ("critical",):
        monkeypatch.setattr(api_main.log, name, lambda *a, **k: levels.append("CRITICAL"))

    api_client(fatal_producer()).post("/boards/Gossiping/crawl")

    assert any(level.upper() == "CRITICAL" for level in levels)


def test_api_non_fatal_kafka_error_returns_503_without_exit(exits):
    p = make(ScriptedProducer(produce_error=KafkaException(plain_err())))

    response = api_client(p).post("/boards/Gossiping/crawl")

    assert response.status_code == 503
    assert exits == []


def test_api_healthy_request_does_not_exit(exits):
    response = api_client(make(FakeProducer(topic_partitions={"crawl.tasks": 3}))).post(
        "/boards/Gossiping/crawl"
    )

    assert response.status_code == 202
    assert exits == []


def test_exit_for_restart_closes_log_then_exits_with_70(monkeypatch):
    order: list[object] = []
    monkeypatch.setattr(log, "close", lambda *a, **k: order.append("close"), raising=False)
    monkeypatch.setattr(api_main.os, "_exit", lambda code: order.append(code))

    api_main.exit_for_restart()

    assert order == ["close", 70]

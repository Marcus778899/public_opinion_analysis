"""#226 scheduler-statement-timeout：Scheduler 的 PG 查詢有逾時，逾時只略過該看板這一輪。

約定的對外介面（實作須照此命名）：
- 環境變數 SCHEDULER_STATEMENT_TIMEOUT_SEC → SchedulerSettings.statement_timeout_sec（秒）
- make_engine(settings, *, pool_size=5, statement_timeout_sec: float | None = None)
"""

from datetime import UTC, datetime, timedelta

import psycopg.errors
import pytest
from sqlalchemy.exc import OperationalError
from tests.unit.common.kafka.fakes import FakeProducer

from radar.collector import scheduler as scheduler_module
from radar.collector.recrawl import DuePost, DuePostDispatcher
from radar.collector.scheduler import make_list_task_sender
from radar.common.db import session as session_module
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import CrawlTask
from radar.common.settings import KafkaSettings, PostgresSettings, SchedulerSettings

NOW = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
LATEST = datetime(2026, 10, 29, 5, 0, tzinfo=UTC)


def timeout_error() -> OperationalError:
    cancelled = psycopg.errors.QueryCanceled("canceling statement due to statement timeout")
    return OperationalError("SELECT max(created_at) ...", {}, cancelled)


class WarningRecorder:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.messages: list[str] = []
        monkeypatch.setattr(
            scheduler_module.log, "warning", lambda *a, **k: self.messages.append(str(a))
        )
        monkeypatch.setattr(
            "radar.collector.recrawl.log.warning", lambda *a, **k: self.messages.append(str(a))
        )


# --- 1. 設定與連線 ---


def test_scheduler_settings_statement_timeout_has_sane_default(monkeypatch):
    monkeypatch.delenv("SCHEDULER_STATEMENT_TIMEOUT_SEC", raising=False)

    value = SchedulerSettings().statement_timeout_sec

    assert 0 < value <= 120


def test_scheduler_settings_statement_timeout_reads_env(monkeypatch):
    monkeypatch.setenv("SCHEDULER_STATEMENT_TIMEOUT_SEC", "7")

    assert SchedulerSettings().statement_timeout_sec == 7


class SpyCreateEngine:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.kwargs: dict[str, object] = {}
        real = session_module.create_engine

        def spy(url, **kwargs):
            self.kwargs = kwargs
            return real(url, **kwargs)

        monkeypatch.setattr(session_module, "create_engine", spy)


def pg_settings() -> PostgresSettings:
    return PostgresSettings(host="h", db="d", user="u", password="p")


def test_make_engine_with_statement_timeout_sets_pg_option_in_ms(monkeypatch):
    spy = SpyCreateEngine(monkeypatch)

    session_module.make_engine(pg_settings(), statement_timeout_sec=7)

    assert "statement_timeout=7000" in str(spy.kwargs.get("connect_args"))
    assert spy.kwargs["pool_size"] == 5
    assert spy.kwargs["pool_pre_ping"] is True


def test_make_engine_default_keeps_existing_behavior(monkeypatch):
    spy = SpyCreateEngine(monkeypatch)

    session_module.make_engine(pg_settings())

    assert spy.kwargs == {"pool_size": 5, "pool_pre_ping": True}


def test_make_engine_custom_pool_size_still_works_without_timeout(monkeypatch):
    spy = SpyCreateEngine(monkeypatch)

    session_module.make_engine(pg_settings(), pool_size=2)

    assert spy.kwargs == {"pool_size": 2, "pool_pre_ping": True}


def test_scheduler_main_builds_engine_with_configured_statement_timeout(monkeypatch):
    monkeypatch.setenv("SCHEDULER_STATEMENT_TIMEOUT_SEC", "7")
    captured: dict[str, object] = {}

    class Engine:
        def dispose(self) -> None:
            pass

    class StandbyLock:
        def __init__(self, *_a, **_k) -> None:
            pass

        def wait_until_acquired(self, **_k) -> bool:
            return False

    def fake_make_engine(_settings, **kwargs):
        captured.update(kwargs)
        return Engine()

    monkeypatch.setattr(scheduler_module, "get_postgres_settings", pg_settings)
    monkeypatch.setattr(scheduler_module, "make_engine", fake_make_engine)
    monkeypatch.setattr(scheduler_module, "AdvisoryLock", StandbyLock)

    scheduler_module.main()

    assert captured.get("statement_timeout_sec") == 7


# --- 2. 逾時：記 WARNING、略過該看板這一輪、下一輪照常 ---


class FlakyEngine:
    """第一次查詢逾時（在 connect 或 execute 階段），之後正常回傳 LATEST。"""

    def __init__(self, fail_at: str) -> None:
        self.fail_at = fail_at
        self.calls = 0

    def connect(self):
        self.calls += 1
        if self.fail_at == "connect" and self.calls == 1:
            raise timeout_error()
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def execute(self, _stmt):
        if self.fail_at == "execute" and self.calls == 1:
            raise timeout_error()
        return self

    def scalar_one(self):
        return LATEST


def make_sender(engine):
    fake = FakeProducer()
    producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake)
    return make_list_task_sender(producer, lambda: [], engine), fake


@pytest.mark.parametrize("fail_at", ["connect", "execute"])
def test_query_timeout_skips_board_this_round_and_logs_warning(monkeypatch, fail_at):
    warnings = WarningRecorder(monkeypatch)
    send, fake = make_sender(FlakyEngine(fail_at))

    send("Stock")

    assert fake.produced == []
    assert any("Stock" in m for m in warnings.messages)


@pytest.mark.parametrize("fail_at", ["connect", "execute"])
def test_query_timeout_next_round_dispatches_normally(monkeypatch, fail_at):
    WarningRecorder(monkeypatch)
    send, fake = make_sender(FlakyEngine(fail_at))

    send("Stock")
    send("Stock")

    assert len(fake.produced) == 1
    task = CrawlTask.model_validate_json(fake.produced[0]["value"])
    assert task.board == "Stock"
    assert task.since == LATEST - timedelta(minutes=10)


def test_query_timeout_on_one_board_does_not_stop_service(monkeypatch):
    WarningRecorder(monkeypatch)
    send, _ = make_sender(FlakyEngine("connect"))

    send("Stock")  # 不可拋出例外


# --- 3. DuePostDispatcher 的查詢逾時 ---


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1


def make_dispatcher(monkeypatch, session, fake_producer, find_due):
    monkeypatch.setattr("radar.collector.recrawl.find_due_posts", find_due)
    monkeypatch.setattr("radar.collector.recrawl.record_dispatch", lambda *a, **k: None)
    producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake_producer)
    return DuePostDispatcher(lambda: session, producer, limit=10, time_scale=1.0)


def test_dispatcher_query_timeout_skips_round_with_warning_then_recovers(monkeypatch):
    warnings = WarningRecorder(monkeypatch)
    session, fake = FakeSession(), FakeProducer()
    calls = {"n": 0}
    post = DuePost("Stock.M.1.A.001", "Stock", "https://www.ptt.cc/bbs/Stock/M.1.A.001.html", NOW)

    def find_due(_session, _now, limit):
        calls["n"] += 1
        if calls["n"] == 1:
            raise timeout_error()
        return [post]

    dispatcher = make_dispatcher(monkeypatch, session, fake, find_due)

    assert dispatcher(NOW) == 0
    assert fake.produced == []
    assert session.commits == 0
    assert warnings.messages != []

    assert dispatcher(NOW) == 1
    assert len(fake.produced) == 1
    assert session.commits == 1


def test_dispatcher_non_timeout_error_still_propagates(monkeypatch):
    WarningRecorder(monkeypatch)

    def find_due(_session, _now, limit):
        raise RuntimeError("bug")

    dispatcher = make_dispatcher(monkeypatch, FakeSession(), FakeProducer(), find_due)

    with pytest.raises(RuntimeError):
        dispatcher(NOW)

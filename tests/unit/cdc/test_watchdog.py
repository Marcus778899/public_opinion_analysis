from contextlib import contextmanager

import httpx2
import pytest
from sqlalchemy.exc import OperationalError

from radar.cdc import watchdog
from radar.cdc.watchdog import (
    AlertChange,
    ConnectorTransition,
    ConnectorWatch,
    SlotAlert,
    SlotInfo,
    SlotWatch,
    check_connector,
    check_slot,
    heartbeat_target,
    is_cdc_healthy,
    run_once,
    send_heartbeat,
)
from radar.common.kafka.connect import ConnectorStatus
from radar.common.settings import CdcWatchdogSettings

RUNNING = ConnectorStatus("RUNNING", ["RUNNING"])
FAILED = ConnectorStatus("RUNNING", ["FAILED"])
RESTARTING = ConnectorStatus("RUNNING", ["RESTARTING"])
HEALTHY_SLOT = SlotInfo(active=True, lag_bytes=100)
HB_URL = "https://hc-ping.com/secret-uuid"


class FakeLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _record(self, level: str, msg: str, *args: object) -> None:
        self.records.append((level, msg % args if args else msg))

    def info(self, msg: str, *args: object) -> None:
        self._record("INFO", msg, *args)

    def warning(self, msg: str, *args: object) -> None:
        self._record("WARNING", msg, *args)

    def error(self, msg: str, *args: object) -> None:
        self._record("ERROR", msg, *args)

    def levels(self) -> list[str]:
        return [level for level, _ in self.records]


@pytest.fixture
def fake_log(monkeypatch) -> FakeLog:
    fake = FakeLog()
    monkeypatch.setattr(watchdog, "log", fake)
    return fake


def connector_watch() -> ConnectorWatch:
    return ConnectorWatch(backoff_initial_s=30, backoff_max_s=100)


def slot_watch() -> SlotWatch:
    return SlotWatch(inactive_alert_s=300, lag_alert_bytes=1000)


# --- ConnectorWatch.observe ---


def test_connector_running_without_prior_failure_does_nothing():
    decision = connector_watch().observe(RUNNING, now=0)

    assert not decision.restart
    assert decision.transition is None


def test_connector_first_failure_restarts_and_reports_failed():
    watch = connector_watch()

    decision = watch.observe(FAILED, now=10)

    assert decision.restart
    assert decision.transition is ConnectorTransition.FAILED
    assert decision.restarts == 1
    assert watch.next_restart_at == 40


def test_connector_still_failed_before_backoff_does_not_restart():
    watch = connector_watch()
    watch.observe(FAILED, now=0)

    decision = watch.observe(FAILED, now=29)

    assert not decision.restart
    assert decision.transition is None


def test_connector_still_failed_after_backoff_restarts_and_doubles_backoff():
    watch = connector_watch()
    watch.observe(FAILED, now=0)

    decision = watch.observe(FAILED, now=30)

    assert decision.restart
    assert decision.transition is None
    assert decision.restarts == 2
    assert watch.backoff_s == 60
    assert watch.next_restart_at == 90


def test_connector_backoff_is_capped_at_max():
    watch = connector_watch()
    watch.observe(FAILED, now=0)
    watch.observe(FAILED, now=30)  # backoff 60
    watch.observe(FAILED, now=90)  # backoff 100（上限）

    decision = watch.observe(FAILED, now=190)

    assert decision.restart
    assert watch.backoff_s == 100
    assert watch.next_restart_at == 290


def test_connector_restarting_after_failure_waits_without_transition():
    watch = connector_watch()
    watch.observe(FAILED, now=0)

    decision = watch.observe(RESTARTING, now=5)

    assert not decision.restart
    assert decision.transition is None
    assert watch.failed_since == 0


def test_connector_running_after_failure_reports_recovered_and_resets_backoff():
    watch = connector_watch()
    watch.observe(FAILED, now=0)
    watch.observe(FAILED, now=30)

    decision = watch.observe(RUNNING, now=35)

    assert decision.transition is ConnectorTransition.RECOVERED
    assert decision.restarts == 2
    assert watch.failed_since is None
    assert watch.backoff_s == 30
    assert watch.restarts == 0


def test_connector_fails_again_after_recovery_restarts_with_initial_backoff():
    watch = connector_watch()
    watch.observe(FAILED, now=0)
    watch.observe(FAILED, now=30)
    watch.observe(RUNNING, now=35)

    decision = watch.observe(FAILED, now=1000)

    assert decision.restart
    assert decision.transition is ConnectorTransition.FAILED
    assert decision.restarts == 1
    assert watch.next_restart_at == 1030


# --- SlotWatch.observe ---


def test_slot_active_with_small_lag_raises_nothing():
    assert slot_watch().observe(HEALTHY_SLOT, now=0) == []


def test_slot_missing_raises_missing_once():
    watch = slot_watch()

    assert watch.observe(None, now=0) == [AlertChange(SlotAlert.MISSING, raised=True)]
    assert watch.observe(None, now=30) == []


def test_slot_inactive_shorter_than_threshold_raises_nothing():
    watch = slot_watch()
    inactive = SlotInfo(active=False, lag_bytes=0)

    assert watch.observe(inactive, now=0) == []
    assert watch.observe(inactive, now=300) == []


def test_slot_inactive_longer_than_threshold_raises_inactive_once():
    watch = slot_watch()
    inactive = SlotInfo(active=False, lag_bytes=0)
    watch.observe(inactive, now=0)

    assert watch.observe(inactive, now=301) == [AlertChange(SlotAlert.INACTIVE, raised=True)]
    assert watch.observe(inactive, now=331) == []


def test_slot_inactive_then_active_clears_inactive_and_resets_timer():
    watch = slot_watch()
    inactive = SlotInfo(active=False, lag_bytes=0)
    watch.observe(inactive, now=0)
    watch.observe(inactive, now=301)

    assert watch.observe(HEALTHY_SLOT, now=331) == [AlertChange(SlotAlert.INACTIVE, raised=False)]
    assert watch.observe(inactive, now=400) == []
    assert watch.observe(inactive, now=650) == []


def test_slot_lag_exactly_at_threshold_raises_nothing():
    assert slot_watch().observe(SlotInfo(active=True, lag_bytes=1000), now=0) == []


def test_slot_lag_above_threshold_raises_lagging_once():
    watch = slot_watch()
    lagging = SlotInfo(active=True, lag_bytes=1001)

    assert watch.observe(lagging, now=0) == [AlertChange(SlotAlert.LAGGING, raised=True)]
    assert watch.observe(lagging, now=30) == []


def test_slot_lag_back_below_threshold_clears_lagging():
    watch = slot_watch()
    watch.observe(SlotInfo(active=True, lag_bytes=5000), now=0)

    assert watch.observe(HEALTHY_SLOT, now=30) == [AlertChange(SlotAlert.LAGGING, raised=False)]


def test_slot_inactive_and_lagging_are_reported_independently():
    watch = slot_watch()
    watch.observe(SlotInfo(active=False, lag_bytes=5000), now=0)

    changes = watch.observe(SlotInfo(active=False, lag_bytes=5000), now=301)
    assert changes == [AlertChange(SlotAlert.INACTIVE, raised=True)]
    assert watch.raised == {SlotAlert.INACTIVE, SlotAlert.LAGGING}

    changes = watch.observe(SlotInfo(active=True, lag_bytes=5000), now=331)
    assert changes == [AlertChange(SlotAlert.INACTIVE, raised=False)]
    assert watch.raised == {SlotAlert.LAGGING}


def test_slot_reappears_after_missing_clears_missing():
    watch = slot_watch()
    watch.observe(None, now=0)

    assert watch.observe(HEALTHY_SLOT, now=30) == [AlertChange(SlotAlert.MISSING, raised=False)]


# --- check_connector / check_slot（IO 以 MockTransport、fake engine 取代）---


def connect_client(status_body: dict | None, restart_code: int = 202) -> tuple[httpx2.Client, list]:
    restarts: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            restarts.append(request)
            return httpx2.Response(restart_code, text="restart response")
        if status_body is None:
            return httpx2.Response(404, text="not found")
        return httpx2.Response(200, json=status_body)

    client = httpx2.Client(base_url="http://connect:8083", transport=httpx2.MockTransport(handler))
    return client, restarts


def status_body(connector: str, *tasks: str) -> dict:
    return {
        "connector": {"state": connector},
        "tasks": [{"id": i, "state": s} for i, s in enumerate(tasks)],
    }


def test_check_connector_failed_calls_restart_and_logs_error(fake_log):
    client, restarts = connect_client(status_body("RUNNING", "FAILED"))

    decision = check_connector(client, "radar-cdc", connector_watch(), now=0)

    assert decision is not None and decision.restart
    assert len(restarts) == 1
    assert fake_log.levels() == ["ERROR", "WARNING"]


def test_check_connector_recovered_logs_info(fake_log):
    watch = connector_watch()
    watch.observe(FAILED, now=0)
    client, restarts = connect_client(status_body("RUNNING", "RUNNING"))

    check_connector(client, "radar-cdc", watch, now=10)

    assert restarts == []
    assert fake_log.levels() == ["INFO"]


def test_check_connector_unreachable_logs_warning_and_returns_none(fake_log):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused")

    client = httpx2.Client(base_url="http://connect:8083", transport=httpx2.MockTransport(handler))
    watch = connector_watch()

    assert check_connector(client, "radar-cdc", watch, now=0) is None
    assert fake_log.levels() == ["WARNING"]
    assert watch.failed_since is None


def test_check_connector_not_found_logs_warning_and_returns_none(fake_log):
    client, restarts = connect_client(None)

    assert check_connector(client, "radar-cdc", connector_watch(), now=0) is None
    assert restarts == []
    assert fake_log.levels() == ["WARNING"]


def test_check_connector_restart_request_fails_logs_warning_and_keeps_backoff(fake_log):
    client, restarts = connect_client(status_body("RUNNING", "FAILED"), restart_code=500)
    watch = connector_watch()

    check_connector(client, "radar-cdc", watch, now=0)

    assert len(restarts) == 1
    assert fake_log.levels() == ["ERROR", "WARNING"]
    assert "restart connector radar-cdc failed" in fake_log.records[1][1]
    assert watch.next_restart_at == 30


class FakeConnection:
    def execute(self, *args: object, **kwargs: object) -> None:
        return None


class FakeEngine:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    @contextmanager
    def connect(self):
        if self.error is not None:
            raise self.error
        yield FakeConnection()


def test_check_slot_raised_alert_logs_error_with_detail(fake_log, monkeypatch):
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: SlotInfo(True, 5000))

    changes = check_slot(FakeEngine(), "radar_cdc", slot_watch(), now=0, statement_timeout_ms=1000)

    assert changes == [AlertChange(SlotAlert.LAGGING, raised=True)]
    assert fake_log.records == [
        ("ERROR", "replication slot radar_cdc lagging: active=True lag_bytes=5000")
    ]


def test_check_slot_cleared_alert_logs_info(fake_log, monkeypatch):
    watch = slot_watch()
    watch.observe(None, now=0)
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: HEALTHY_SLOT)

    check_slot(FakeEngine(), "radar_cdc", watch, now=30, statement_timeout_ms=1000)

    assert fake_log.levels() == ["INFO"]


def test_check_slot_query_error_logs_warning_and_keeps_alert_state(fake_log):
    watch = slot_watch()
    watch.observe(SlotInfo(True, 5000), now=0)
    engine = FakeEngine(OperationalError("SELECT", {}, Exception("timeout")))

    assert check_slot(engine, "radar_cdc", watch, now=30, statement_timeout_ms=1000) == []
    assert fake_log.levels() == ["WARNING"]
    assert watch.raised == {SlotAlert.LAGGING}


# --- heartbeat ---


def test_is_cdc_healthy_running_connector_and_no_slot_alert_is_healthy():
    assert is_cdc_healthy(connector_watch(), slot_watch())


def test_is_cdc_healthy_failed_connector_is_unhealthy():
    watch = connector_watch()
    watch.observe(FAILED, now=0)

    assert not is_cdc_healthy(watch, slot_watch())


def test_is_cdc_healthy_any_slot_alert_is_unhealthy():
    slots = slot_watch()
    slots.observe(None, now=0)

    assert not is_cdc_healthy(connector_watch(), slots)


def test_heartbeat_target_healthy_is_base_url():
    assert heartbeat_target(HB_URL, healthy=True) == HB_URL


def test_heartbeat_target_unhealthy_appends_fail():
    assert heartbeat_target(HB_URL, healthy=False) == f"{HB_URL}/fail"


def test_heartbeat_target_trailing_slash_is_not_doubled():
    assert heartbeat_target(f"{HB_URL}/", healthy=False) == f"{HB_URL}/fail"
    assert heartbeat_target(f"{HB_URL}/", healthy=True) == HB_URL


def heartbeat_client(code: int = 200) -> tuple[httpx2.Client, list[str]]:
    pinged: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        pinged.append(str(request.url))
        return httpx2.Response(code)

    return httpx2.Client(transport=httpx2.MockTransport(handler)), pinged


def test_send_heartbeat_success_returns_true(fake_log):
    client, pinged = heartbeat_client()

    assert send_heartbeat(client, HB_URL, healthy=True)
    assert pinged == [HB_URL]
    assert fake_log.records == []


def test_send_heartbeat_unreachable_logs_warning_without_url_and_returns_false(fake_log):
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError(f"cannot reach {request.url}")

    client = httpx2.Client(transport=httpx2.MockTransport(handler))

    assert not send_heartbeat(client, HB_URL, healthy=True)
    assert fake_log.levels() == ["WARNING"]
    assert "secret-uuid" not in fake_log.records[0][1]


def test_send_heartbeat_non_2xx_returns_false(fake_log):
    client, _ = heartbeat_client(code=404)

    assert not send_heartbeat(client, HB_URL, healthy=True)
    assert fake_log.levels() == ["WARNING"]


# --- run_once ---


def settings_with(heartbeat_url: str | None) -> CdcWatchdogSettings:
    return CdcWatchdogSettings(heartbeat_url=heartbeat_url)


def test_run_once_healthy_pings_base_url(fake_log, monkeypatch):
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: HEALTHY_SLOT)
    connect, _ = connect_client(status_body("RUNNING", "RUNNING"))
    hb, pinged = heartbeat_client()

    run_once(
        connect, FakeEngine(), hb, connector_watch(), slot_watch(), settings_with(HB_URL), now=0
    )

    assert pinged == [HB_URL]


def test_run_once_connector_failed_pings_fail(fake_log, monkeypatch):
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: HEALTHY_SLOT)
    connect, restarts = connect_client(status_body("RUNNING", "FAILED"))
    hb, pinged = heartbeat_client()

    run_once(
        connect, FakeEngine(), hb, connector_watch(), slot_watch(), settings_with(HB_URL), now=0
    )

    assert len(restarts) == 1
    assert pinged == [f"{HB_URL}/fail"]


def test_run_once_connect_unreachable_still_pings_healthy(fake_log, monkeypatch):
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: HEALTHY_SLOT)

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("connection refused")

    connect = httpx2.Client(base_url="http://connect:8083", transport=httpx2.MockTransport(refuse))
    hb, pinged = heartbeat_client()

    run_once(
        connect, FakeEngine(), hb, connector_watch(), slot_watch(), settings_with(HB_URL), now=0
    )

    assert pinged == [HB_URL]


def test_run_once_without_heartbeat_client_skips_ping(fake_log, monkeypatch):
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: HEALTHY_SLOT)
    connect, _ = connect_client(status_body("RUNNING", "RUNNING"))

    run_once(
        connect, FakeEngine(), None, connector_watch(), slot_watch(), settings_with(None), now=0
    )

    assert fake_log.records == []

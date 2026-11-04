"""驗收 pipeline-stall-alert（開發規格 7.28 B）：ClickHouse 最新 changed_at 太久沒更新就告警。

worker 需提供的介面（見 watchdog.py）：
- FreshnessWatch(stale_alert_s, started_at).observe(latest, now) -> FreshnessTransition | None
  latest=None 表示查不到（查詢失敗或表是空的），沿用上次的值；.stalled 為目前是否停擺
- read_latest_changed_at(client) -> datetime | None（UTC aware）
- check_freshness(client, watch, now) -> FreshnessTransition | None，負責 log
- is_cdc_healthy(connector, slot, freshness=None)
- run_once(..., *, clickhouse=None, freshness_watch=None, wall_now=None)
"""

import re
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from radar.cdc import watchdog
from radar.cdc.watchdog import (
    ConnectorWatch,
    FreshnessTransition,
    FreshnessWatch,
    SlotInfo,
    SlotWatch,
    check_freshness,
    is_cdc_healthy,
    run_once,
)
from radar.common.clickhouse import ClickHouseClient, ClickHouseError
from radar.common.settings import CdcWatchdogSettings, ClickHouseSettings

REPO = Path(__file__).resolve().parents[4]
T0 = datetime(2026, 10, 29, 0, 0, tzinfo=UTC)
ALERT_S = 1800.0
HB_URL = "https://hc-ping.com/secret-uuid"


def secs(n: float) -> timedelta:
    return timedelta(seconds=n)


def watch(started_at: datetime = T0) -> FreshnessWatch:
    return FreshnessWatch(ALERT_S, started_at)


class FakeLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _r(self, level: str, msg: str, *args: object) -> None:
        self.records.append((level, msg % args if args else msg))

    def info(self, msg: str, *args: object) -> None:
        self._r("INFO", msg, *args)

    def warning(self, msg: str, *args: object) -> None:
        self._r("WARNING", msg, *args)

    def error(self, msg: str, *args: object) -> None:
        self._r("ERROR", msg, *args)

    def levels(self) -> list[str]:
        return [lv for lv, _ in self.records]


@pytest.fixture
def fake_log(monkeypatch) -> FakeLog:
    fake = FakeLog()
    monkeypatch.setattr(watchdog, "log", fake)
    return fake


# --- FreshnessWatch 純邏輯 ---


def test_data_fresher_than_threshold_raises_nothing():
    w = watch()
    assert w.observe(T0, T0 + secs(ALERT_S - 1)) is None
    assert not w.stalled


def test_lag_exactly_at_threshold_raises_nothing():
    w = watch()
    assert w.observe(T0, T0 + secs(ALERT_S)) is None
    assert not w.stalled


def test_lag_just_over_threshold_raises_stalled():
    w = watch()
    assert w.observe(T0, T0 + secs(ALERT_S + 1)) is FreshnessTransition.STALLED
    assert w.stalled


def test_stalled_reported_only_once_while_still_stale():
    w = watch()
    assert w.observe(T0, T0 + secs(ALERT_S + 1)) is FreshnessTransition.STALLED
    assert w.observe(T0, T0 + secs(ALERT_S + 60)) is None
    assert w.observe(T0, T0 + secs(ALERT_S * 5)) is None
    assert w.stalled


def test_new_data_after_stall_reports_recovered_once():
    w = watch()
    w.observe(T0, T0 + secs(ALERT_S + 1))
    now = T0 + secs(ALERT_S + 100)
    assert w.observe(now - secs(5), now) is FreshnessTransition.RECOVERED
    assert not w.stalled
    assert w.observe(now - secs(5), now + secs(10)) is None


def test_stall_can_be_raised_again_after_recovery():
    w = watch()
    w.observe(T0, T0 + secs(ALERT_S + 1))
    t1 = T0 + secs(ALERT_S + 100)
    w.observe(t1, t1)
    assert w.observe(t1, t1 + secs(ALERT_S + 1)) is FreshnessTransition.STALLED


def test_startup_time_is_floor_when_data_is_older_than_watchdog_start():
    # 資料很舊但 watchdog 剛啟動：從啟動時間起算，不能一開機就告警
    started = T0 + secs(10 * 3600)
    w = watch(started_at=started)
    assert w.observe(T0, started + secs(ALERT_S - 1)) is None
    assert w.observe(T0, started + secs(ALERT_S + 1)) is FreshnessTransition.STALLED


def test_empty_table_counts_from_startup_time():
    w = watch()
    assert w.observe(None, T0 + secs(ALERT_S - 1)) is None
    assert w.observe(None, T0 + secs(ALERT_S + 1)) is FreshnessTransition.STALLED


def test_failed_query_keeps_last_known_value_and_alerts_after_threshold():
    w = watch()
    last = T0 + secs(100)
    assert w.observe(last, last + secs(10)) is None
    assert w.observe(None, last + secs(ALERT_S - 1)) is None
    assert w.observe(None, last + secs(ALERT_S + 1)) is FreshnessTransition.STALLED


def test_failed_query_does_not_clear_stalled_state():
    w = watch()
    w.observe(T0, T0 + secs(ALERT_S + 1))
    assert w.observe(None, T0 + secs(ALERT_S + 100)) is None
    assert w.stalled


# --- check_freshness（IO 與 log）---


def ch_client(handler) -> ClickHouseClient:
    settings = ClickHouseSettings(url="http://ch:8123", user="u", password="p")
    return ClickHouseClient(settings, transport=httpx2.MockTransport(handler))


def ch_returning(value: str) -> ClickHouseClient:
    # 不管 worker 用 TSV 或 JSONEachRow 讀，都回得出同一個時間
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = request.content.decode()
        if "JSONEachRow" in body:
            return httpx2.Response(
                200, text=f'{{"latest": "{value}", "max(changed_at)": "{value}"}}\n'
            )
        return httpx2.Response(200, text=f"{value}\n")

    return ch_client(handler)


def test_check_freshness_stalled_logs_error_once(fake_log, monkeypatch):
    monkeypatch.setattr(watchdog, "read_latest_changed_at", lambda c: T0)
    w = watch()
    now = T0 + secs(ALERT_S + 1)

    assert check_freshness(object(), w, now) is FreshnessTransition.STALLED
    assert check_freshness(object(), w, now + secs(30)) is None
    assert fake_log.levels() == ["ERROR"]


def test_check_freshness_fresh_data_logs_nothing(fake_log, monkeypatch):
    monkeypatch.setattr(watchdog, "read_latest_changed_at", lambda c: T0)
    assert check_freshness(object(), watch(), T0 + secs(60)) is None
    assert fake_log.records == []


def test_check_freshness_recovery_logs_info_once(fake_log, monkeypatch):
    latest = [T0]
    monkeypatch.setattr(watchdog, "read_latest_changed_at", lambda c: latest[0])
    w = watch()
    check_freshness(object(), w, T0 + secs(ALERT_S + 1))
    latest[0] = T0 + secs(ALERT_S + 50)
    now = T0 + secs(ALERT_S + 60)

    assert check_freshness(object(), w, now) is FreshnessTransition.RECOVERED
    assert check_freshness(object(), w, now + secs(30)) is None
    assert fake_log.levels() == ["ERROR", "INFO"]


@pytest.mark.parametrize(
    "error", [ClickHouseError("500: boom"), httpx2.ConnectError("refused")], ids=["http500", "conn"]
)
def test_check_freshness_query_error_logs_warning_and_keeps_state(fake_log, monkeypatch, error):
    def boom(c):
        raise error

    monkeypatch.setattr(watchdog, "read_latest_changed_at", boom)
    w = watch()

    assert check_freshness(object(), w, T0 + secs(60)) is None
    assert fake_log.levels() == ["WARNING"]
    assert not w.stalled


def test_check_freshness_query_error_past_threshold_still_alerts(fake_log, monkeypatch):
    def boom(c):
        raise ClickHouseError("down")

    monkeypatch.setattr(watchdog, "read_latest_changed_at", boom)
    w = watch()

    assert check_freshness(object(), w, T0 + secs(ALERT_S + 1)) is FreshnessTransition.STALLED
    assert fake_log.levels() == ["WARNING", "ERROR"]


def test_read_latest_changed_at_parses_utc_datetime():
    from radar.cdc.watchdog import read_latest_changed_at

    got = read_latest_changed_at(ch_returning("2026-10-29 01:02:03.456"))
    assert got == datetime(2026, 10, 29, 1, 2, 3, 456000, tzinfo=UTC)


# --- heartbeat ---


RUNNING_BODY = {"connector": {"state": "RUNNING"}, "tasks": [{"id": 0, "state": "RUNNING"}]}


def test_is_cdc_healthy_stalled_pipeline_is_unhealthy():
    w = watch()
    w.observe(T0, T0 + secs(ALERT_S + 1))
    assert not is_cdc_healthy(ConnectorWatch(30, 100), SlotWatch(300, 1000), w)


def test_is_cdc_healthy_fresh_pipeline_is_healthy():
    assert is_cdc_healthy(ConnectorWatch(30, 100), SlotWatch(300, 1000), watch())


def test_is_cdc_healthy_without_freshness_watch_keeps_old_behaviour():
    assert is_cdc_healthy(ConnectorWatch(30, 100), SlotWatch(300, 1000))


class FakeConnection:
    def execute(self, *args: object, **kwargs: object) -> None:
        return None


class FakeEngine:
    @contextmanager
    def connect(self):
        yield FakeConnection()


def run_round(monkeypatch, latest: datetime, wall_now: datetime, w: FreshnessWatch) -> list[str]:
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: SlotInfo(True, 100))
    monkeypatch.setattr(watchdog, "read_latest_changed_at", lambda c: latest)
    pinged: list[str] = []

    def hb(request: httpx2.Request) -> httpx2.Response:
        pinged.append(str(request.url))
        return httpx2.Response(200)

    def connect(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=RUNNING_BODY)

    run_once(
        httpx2.Client(base_url="http://connect:8083", transport=httpx2.MockTransport(connect)),
        FakeEngine(),
        httpx2.Client(transport=httpx2.MockTransport(hb)),
        ConnectorWatch(30, 100),
        SlotWatch(300, 1000),
        CdcWatchdogSettings(heartbeat_url=HB_URL),
        now=0,
        clickhouse=object(),
        freshness_watch=w,
        wall_now=wall_now,
    )
    return pinged


def test_run_once_pipeline_stalled_pings_fail(fake_log, monkeypatch):
    pinged = run_round(monkeypatch, T0, T0 + secs(ALERT_S + 1), watch())
    assert pinged == [f"{HB_URL}/fail"]


def test_run_once_pipeline_fresh_pings_base_url(fake_log, monkeypatch):
    pinged = run_round(monkeypatch, T0, T0 + secs(60), watch())
    assert pinged == [HB_URL]


def test_run_once_pipeline_recovers_pings_base_url_again(fake_log, monkeypatch):
    w = watch()
    assert run_round(monkeypatch, T0, T0 + secs(ALERT_S + 1), w) == [f"{HB_URL}/fail"]
    later = T0 + secs(ALERT_S + 100)
    assert run_round(monkeypatch, later - secs(3), later, w) == [HB_URL]


# --- 設定 ---


def test_settings_stale_alert_default_is_1800_seconds(monkeypatch):
    monkeypatch.delenv("CDC_WATCHDOG_STALE_ALERT_S", raising=False)
    assert CdcWatchdogSettings().stale_alert_s == 1800


def test_settings_stale_alert_reads_env(monkeypatch):
    monkeypatch.setenv("CDC_WATCHDOG_STALE_ALERT_S", "600")
    assert CdcWatchdogSettings().stale_alert_s == 600


def test_env_example_documents_stale_alert_as_commented_optional():
    lines = (REPO / ".env.example").read_text().splitlines()
    assert "# CDC_WATCHDOG_STALE_ALERT_S=1800" in lines
    assert not any(re.match(r"^CDC_WATCHDOG_STALE_ALERT_S=", ln) for ln in lines)


# --- ClickHouseClient timeout_s ---


def seen_timeout(**kwargs) -> dict:
    seen: dict = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.update(request.extensions["timeout"])
        return httpx2.Response(200, text="")

    settings = ClickHouseSettings(url="http://ch:8123", user="u", password="p")
    ClickHouseClient(settings, transport=httpx2.MockTransport(handler), **kwargs).execute(
        "SELECT 1"
    )
    return seen


def test_clickhouse_client_default_timeout_stays_30_seconds():
    assert seen_timeout()["read"] == 30.0


def test_clickhouse_client_timeout_s_overrides_request_timeout():
    assert seen_timeout(timeout_s=7.5)["read"] == 7.5

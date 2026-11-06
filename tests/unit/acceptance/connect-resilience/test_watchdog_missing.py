"""驗收 connect-resilience（開發規格 7.30 B）：watchdog 對 connector 404 的處理。

worker 需提供的介面（watchdog.py、settings.py）：
- CdcWatchdogSettings.connector_missing_alert_s，預設 300.0
  （env CDC_WATCHDOG_CONNECTOR_MISSING_ALERT_S）
- MissingWatch(alert_s).observe(found: bool, now: float) -> MissingTransition | None；.alerting 屬性
  MissingTransition 有 MISSING（第一次沒找到）、ALERT（持續超過 alert_s，嚴格大於）、
  RECOVERED（告警後找到）。其他情況回 None
- check_connector(client, name, watch, now, *, missing_watch=None)：404 時才呼叫
  observe(False, now)；
  成功取得狀態呼叫 observe(True, now)；Connect 連不上／5xx 不呼叫
- is_cdc_healthy(connector, slot, freshness=None, missing=None)
- run_once(..., *, missing_watch=None)
"""

from contextlib import contextmanager

import httpx2
import pytest

from radar.cdc import watchdog
from radar.cdc.watchdog import (
    ConnectorWatch,
    MissingTransition,
    MissingWatch,
    SlotInfo,
    SlotWatch,
    check_connector,
    is_cdc_healthy,
    run_once,
)
from radar.common.settings import CdcWatchdogSettings

ALERT_S = 300.0
HB_URL = "https://hc-ping.com/secret-uuid"
RUNNING_BODY = {"connector": {"state": "RUNNING"}, "tasks": [{"id": 0, "state": "RUNNING"}]}


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


# --- settings ---


def test_settings_connector_missing_alert_default_300s() -> None:
    assert CdcWatchdogSettings().connector_missing_alert_s == 300.0


def test_settings_connector_missing_alert_reads_env(monkeypatch) -> None:
    monkeypatch.setenv("CDC_WATCHDOG_CONNECTOR_MISSING_ALERT_S", "42")
    assert CdcWatchdogSettings().connector_missing_alert_s == 42.0


# --- MissingWatch 純邏輯 ---


def test_missing_first_observation_reports_missing_not_alert() -> None:
    w = MissingWatch(ALERT_S)
    assert w.observe(False, 0) is MissingTransition.MISSING
    assert not w.alerting


def test_missing_found_from_start_reports_nothing() -> None:
    w = MissingWatch(ALERT_S)
    assert w.observe(True, 0) is None
    assert not w.alerting


def test_missing_repeated_before_threshold_reports_nothing() -> None:
    w = MissingWatch(ALERT_S)
    w.observe(False, 0)
    assert w.observe(False, 30) is None
    assert w.observe(False, ALERT_S) is None  # 剛好等於門檻還不算超過
    assert not w.alerting


def test_missing_past_threshold_raises_alert_once() -> None:
    w = MissingWatch(ALERT_S)
    w.observe(False, 0)
    assert w.observe(False, ALERT_S + 1) is MissingTransition.ALERT
    assert w.alerting
    assert w.observe(False, ALERT_S + 31) is None
    assert w.observe(False, ALERT_S * 10) is None
    assert w.alerting


def test_missing_found_after_alert_reports_recovered_once() -> None:
    w = MissingWatch(ALERT_S)
    w.observe(False, 0)
    w.observe(False, ALERT_S + 1)
    assert w.observe(True, ALERT_S + 31) is MissingTransition.RECOVERED
    assert not w.alerting
    assert w.observe(True, ALERT_S + 61) is None


def test_missing_found_before_threshold_resets_timer() -> None:
    w = MissingWatch(ALERT_S)
    w.observe(False, 0)
    w.observe(True, 100)
    assert not w.alerting
    # 計時重來：從 200 起算，到 200 + 門檻 以內不告警
    assert w.observe(False, 200) is MissingTransition.MISSING
    assert w.observe(False, 200 + ALERT_S) is None
    assert w.observe(False, 200 + ALERT_S + 1) is MissingTransition.ALERT


def test_missing_second_episode_alerts_again_after_recovery() -> None:
    w = MissingWatch(ALERT_S)
    w.observe(False, 0)
    w.observe(False, ALERT_S + 1)
    w.observe(True, ALERT_S + 2)
    assert w.observe(False, 1000) is MissingTransition.MISSING
    assert w.observe(False, 1000 + ALERT_S + 1) is MissingTransition.ALERT


# --- check_connector（IO 與 log）---


def connect_client(handler) -> httpx2.Client:
    return httpx2.Client(base_url="http://connect:8083", transport=httpx2.MockTransport(handler))


def not_found(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(404, json={"error_code": 404, "message": "not found"})


def found(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json=RUNNING_BODY)


def cw() -> ConnectorWatch:
    return ConnectorWatch(30, 600)


def test_check_connector_404_before_threshold_logs_single_warning(fake_log) -> None:
    mw = MissingWatch(ALERT_S)
    client = connect_client(not_found)

    for now in (0, 30, 60, 90, 120):
        check_connector(client, "radar-cdc", cw(), now, missing_watch=mw)

    assert fake_log.levels() == ["WARNING"]


def test_check_connector_404_past_threshold_logs_error_once(fake_log) -> None:
    mw = MissingWatch(ALERT_S)
    client = connect_client(not_found)

    for now in (0, 30, ALERT_S + 1, ALERT_S + 31, ALERT_S + 61):
        check_connector(client, "radar-cdc", cw(), now, missing_watch=mw)

    assert fake_log.levels() == ["WARNING", "ERROR"]
    assert "radar-cdc" in fake_log.records[1][1]


def test_check_connector_found_after_alert_logs_info_once(fake_log) -> None:
    mw = MissingWatch(ALERT_S)
    check_connector(connect_client(not_found), "radar-cdc", cw(), 0, missing_watch=mw)
    check_connector(connect_client(not_found), "radar-cdc", cw(), ALERT_S + 1, missing_watch=mw)
    fake_log.records.clear()

    check_connector(connect_client(found), "radar-cdc", cw(), ALERT_S + 31, missing_watch=mw)
    check_connector(connect_client(found), "radar-cdc", cw(), ALERT_S + 61, missing_watch=mw)

    assert fake_log.levels() == ["INFO"]
    assert not mw.alerting


def test_check_connector_unreachable_does_not_change_missing_state(fake_log) -> None:
    mw = MissingWatch(ALERT_S)
    check_connector(connect_client(not_found), "radar-cdc", cw(), 0, missing_watch=mw)

    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    # 連不上不算 404，也不算找到；之後仍照原本起算時間告警
    check_connector(connect_client(refuse), "radar-cdc", cw(), 100, missing_watch=mw)
    check_connector(connect_client(not_found), "radar-cdc", cw(), ALERT_S + 1, missing_watch=mw)

    assert mw.alerting
    assert "ERROR" in fake_log.levels()


def test_check_connector_server_error_does_not_start_missing_timer(fake_log) -> None:
    mw = MissingWatch(ALERT_S)
    client = connect_client(lambda r: httpx2.Response(500, text="boom"))

    for now in (0, ALERT_S + 1, ALERT_S * 3):
        check_connector(client, "radar-cdc", cw(), now, missing_watch=mw)

    assert not mw.alerting
    assert "ERROR" not in fake_log.levels()


def test_check_connector_without_missing_watch_keeps_legacy_warning(fake_log) -> None:
    check_connector(connect_client(not_found), "radar-cdc", cw(), 0)
    assert fake_log.levels() == ["WARNING"]


# --- is_cdc_healthy / run_once ---


def test_is_cdc_healthy_missing_alerting_is_unhealthy() -> None:
    mw = MissingWatch(ALERT_S)
    mw.observe(False, 0)
    mw.observe(False, ALERT_S + 1)
    assert not is_cdc_healthy(cw(), SlotWatch(300, 1000), missing=mw)


def test_is_cdc_healthy_missing_before_threshold_is_healthy() -> None:
    mw = MissingWatch(ALERT_S)
    mw.observe(False, 0)
    assert is_cdc_healthy(cw(), SlotWatch(300, 1000), missing=mw)


class FakeConnection:
    def execute(self, *a, **k):
        return None


class FakeEngine:
    @contextmanager
    def connect(self):
        yield FakeConnection()


def run_round(monkeypatch, handler, mw: MissingWatch, now: float) -> list[str]:
    monkeypatch.setattr(watchdog, "read_slot", lambda conn, name: SlotInfo(True, 100))
    pinged: list[str] = []

    def hb(request: httpx2.Request) -> httpx2.Response:
        pinged.append(str(request.url))
        return httpx2.Response(200)

    run_once(
        connect_client(handler),
        FakeEngine(),
        httpx2.Client(transport=httpx2.MockTransport(hb)),
        cw(),
        SlotWatch(300, 1000),
        CdcWatchdogSettings(heartbeat_url=HB_URL),
        now=now,
        missing_watch=mw,
    )
    return pinged


def test_run_once_missing_past_threshold_pings_fail(fake_log, monkeypatch) -> None:
    mw = MissingWatch(ALERT_S)
    run_round(monkeypatch, not_found, mw, 0)
    assert run_round(monkeypatch, not_found, mw, ALERT_S + 1) == [f"{HB_URL}/fail"]


def test_run_once_missing_before_threshold_pings_base_url(fake_log, monkeypatch) -> None:
    mw = MissingWatch(ALERT_S)
    assert run_round(monkeypatch, not_found, mw, 0) == [HB_URL]


def test_run_once_connector_back_pings_base_url_again(fake_log, monkeypatch) -> None:
    mw = MissingWatch(ALERT_S)
    run_round(monkeypatch, not_found, mw, 0)
    run_round(monkeypatch, not_found, mw, ALERT_S + 1)
    assert run_round(monkeypatch, found, mw, ALERT_S + 31) == [HB_URL]

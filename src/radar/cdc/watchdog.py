"""CDC watchdog（設計文件 6.4、開發規格 7.16）：task 失敗時自動重啟，slot 異常時記 ERROR。

狀態判斷（`ConnectorWatch`、`SlotWatch`）是純邏輯，時間由呼叫端傳入；IO 與 log 集中在 `check_*`。
"""

import signal
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import httpx2
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from radar.common.clickhouse import ClickHouseClient, ClickHouseError
from radar.common.kafka.connect import (
    ConnectError,
    ConnectorNotFoundError,
    ConnectorStatus,
    get_status,
    restart_failed,
)
from radar.common.log import log, setup_logging
from radar.common.settings import (
    CdcWatchdogSettings,
    ClickHouseSettings,
    ConnectSettings,
    get_postgres_settings,
)


class ConnectorTransition(StrEnum):
    FAILED = "failed"
    RECOVERED = "recovered"


@dataclass(frozen=True)
class ConnectorDecision:
    restart: bool
    transition: ConnectorTransition | None = None
    # 到目前為止的重啟次數；RECOVERED 時是恢復前總共重啟了幾次
    restarts: int = 0


class ConnectorWatch:
    """依 connector 狀態決定是否重啟；重啟後仍失敗，下次重啟的間隔加倍。"""

    def __init__(self, backoff_initial_s: float, backoff_max_s: float) -> None:
        self._backoff_initial_s = backoff_initial_s
        self._backoff_max_s = backoff_max_s
        self.failed_since: float | None = None
        self.next_restart_at: float | None = None
        self.backoff_s = backoff_initial_s
        self.restarts = 0

    def observe(self, status: ConnectorStatus, now: float) -> ConnectorDecision:
        if status.is_failed:
            if self.failed_since is None:
                self.failed_since = now
                self.backoff_s = self._backoff_initial_s
                return self._restart(now, ConnectorTransition.FAILED)
            if self.next_restart_at is not None and now >= self.next_restart_at:
                self.backoff_s = min(self.backoff_s * 2, self._backoff_max_s)
                return self._restart(now, None)
            return ConnectorDecision(restart=False, restarts=self.restarts)

        # NOTE: 重啟後會先經過 RESTARTING／UNASSIGNED，全部 RUNNING 才算恢復
        if status.is_running and self.failed_since is not None:
            restarts = self.restarts
            self.failed_since = None
            self.next_restart_at = None
            self.backoff_s = self._backoff_initial_s
            self.restarts = 0
            return ConnectorDecision(
                restart=False, transition=ConnectorTransition.RECOVERED, restarts=restarts
            )
        return ConnectorDecision(restart=False, restarts=self.restarts)

    def _restart(self, now: float, transition: ConnectorTransition | None) -> ConnectorDecision:
        self.restarts += 1
        self.next_restart_at = now + self.backoff_s
        return ConnectorDecision(restart=True, transition=transition, restarts=self.restarts)


@dataclass(frozen=True)
class SlotInfo:
    active: bool
    lag_bytes: int


class SlotAlert(StrEnum):
    MISSING = "missing"
    INACTIVE = "inactive"
    LAGGING = "lagging"


@dataclass(frozen=True)
class AlertChange:
    alert: SlotAlert
    raised: bool


class SlotWatch:
    """只在警示狀態改變時回報，避免每一輪都記 ERROR。"""

    def __init__(self, inactive_alert_s: float, lag_alert_bytes: int) -> None:
        self._inactive_alert_s = inactive_alert_s
        self._lag_alert_bytes = lag_alert_bytes
        self.inactive_since: float | None = None
        self.raised: set[SlotAlert] = set()

    def observe(self, info: SlotInfo | None, now: float) -> list[AlertChange]:
        current: set[SlotAlert] = set()
        if info is None:
            self.inactive_since = None
            current.add(SlotAlert.MISSING)
        else:
            if info.active:
                self.inactive_since = None
            else:
                if self.inactive_since is None:
                    self.inactive_since = now
                if now - self.inactive_since > self._inactive_alert_s:
                    current.add(SlotAlert.INACTIVE)
            if info.lag_bytes > self._lag_alert_bytes:
                current.add(SlotAlert.LAGGING)

        changes = [AlertChange(a, raised=True) for a in SlotAlert if a in current - self.raised]
        changes += [AlertChange(a, raised=False) for a in SlotAlert if a in self.raised - current]
        self.raised = current
        return changes


_SLOT_QUERY = text(
    """
    SELECT active,
           COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(),
                                    COALESCE(confirmed_flush_lsn, restart_lsn)), 0)::bigint
    FROM pg_replication_slots
    WHERE slot_name = :slot_name
    """
)


def read_slot(conn: Connection, slot_name: str) -> SlotInfo | None:
    # NOTE: confirmed_flush_lsn 在從未 flush 時是 NULL；slot 失效時兩個 LSN 都是 NULL，lag 記 0
    row = conn.execute(_SLOT_QUERY, {"slot_name": slot_name}).one_or_none()
    if row is None:
        return None
    return SlotInfo(active=bool(row[0]), lag_bytes=int(row[1]))


def check_connector(
    client: httpx2.Client, name: str, watch: ConnectorWatch, now: float
) -> ConnectorDecision | None:
    """查狀態、依決定重啟並記 log；Connect 連不上或 connector 不存在時記 WARNING 回 None。"""
    try:
        status = get_status(client, name)
    except ConnectorNotFoundError:
        log.warning("connector %s not found", name)
        return None
    except (ConnectError, httpx2.HTTPError, KeyError, ValueError) as e:
        log.warning("kafka connect status unavailable: %r", e)
        return None

    decision = watch.observe(status, now)
    if decision.transition is ConnectorTransition.FAILED:
        log.error("connector %s failed, restarting: %s", name, status)
    elif decision.transition is ConnectorTransition.RECOVERED:
        log.info("connector %s recovered after %d restart(s)", name, decision.restarts)

    if decision.restart:
        try:
            restart_failed(client, name)
        except (ConnectError, httpx2.HTTPError) as e:
            log.warning("restart connector %s failed: %r", name, e)
        else:
            log.warning(
                "restarted connector %s (attempt %d, next retry in %.0fs if still failed)",
                name,
                decision.restarts,
                watch.backoff_s,
            )
    return decision


def check_slot(
    engine: Engine, slot_name: str, watch: SlotWatch, now: float, statement_timeout_ms: int
) -> list[AlertChange]:
    """查 slot 並記 log；查詢失敗記 WARNING 回空 list（不改變警示狀態）。"""
    try:
        with engine.connect() as conn:
            conn.execute(
                text("SELECT set_config('statement_timeout', :ms, true)"),
                {"ms": str(statement_timeout_ms)},
            )
            info = read_slot(conn, slot_name)
    except SQLAlchemyError as e:
        log.warning("read replication slot %s failed: %r", slot_name, e)
        return []

    changes = watch.observe(info, now)
    detail = "not found" if info is None else f"active={info.active} lag_bytes={info.lag_bytes}"
    for change in changes:
        if change.raised:
            log.error("replication slot %s %s: %s", slot_name, change.alert, detail)
        else:
            log.info("replication slot %s no longer %s: %s", slot_name, change.alert, detail)
    return changes


class FreshnessTransition(StrEnum):
    STALLED = "stalled"
    RECOVERED = "recovered"


class FreshnessWatch:
    """ClickHouse 最新 changed_at 太久沒前進就算停擺（開發規格 7.28 B）；只在狀態改變時回報。"""

    def __init__(self, stale_alert_s: float, started_at: datetime) -> None:
        self._stale_alert = timedelta(seconds=stale_alert_s)
        self._started_at = started_at
        self._latest: datetime | None = None
        self.stalled = False

    def observe(self, latest: datetime | None, now: datetime) -> FreshnessTransition | None:
        # NOTE: latest 為 None（查詢失敗或空表）時沿用舊值；啟動時間當下限，避免一開機就告警
        if latest is not None and (self._latest is None or latest > self._latest):
            self._latest = latest
        baseline = self._started_at if self._latest is None else max(self._latest, self._started_at)
        stalled = now - baseline > self._stale_alert
        if stalled == self.stalled:
            return None
        self.stalled = stalled
        return FreshnessTransition.STALLED if stalled else FreshnessTransition.RECOVERED


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def read_latest_changed_at(client: ClickHouseClient) -> datetime | None:
    """posts_history 最新的 changed_at（UTC）；空表（ClickHouse 回 epoch）回 None。"""
    rows = client.query_rows("SELECT max(changed_at) AS latest FROM posts_history")
    if not rows:
        return None
    latest = datetime.fromisoformat(str(rows[0]["latest"])).replace(tzinfo=UTC)
    return None if latest <= _EPOCH else latest


def check_freshness(
    client: ClickHouseClient, watch: FreshnessWatch, now: datetime
) -> FreshnessTransition | None:
    """查最新資料時間並記 log；查詢失敗記 WARNING、沿用上次的值。"""
    latest: datetime | None = None
    try:
        latest = read_latest_changed_at(client)
    except (ClickHouseError, httpx2.HTTPError, KeyError, ValueError) as e:
        log.warning("read latest changed_at failed: %r", e)

    transition = watch.observe(latest, now)
    if transition is FreshnessTransition.STALLED:
        log.error("pipeline stalled: no new posts_history rows (latest changed_at %s)", latest)
    elif transition is FreshnessTransition.RECOVERED:
        log.info("pipeline recovered: posts_history is receiving new rows again")
    return transition


def is_cdc_healthy(
    connector: ConnectorWatch, slot: SlotWatch, freshness: FreshnessWatch | None = None
) -> bool:
    # NOTE: Connect 連不上不算異常；停太久時 slot 會 inactive，由 slot 警示涵蓋（開發規格 7.16）
    if freshness is not None and freshness.stalled:
        return False
    return connector.failed_since is None and not slot.raised


def heartbeat_target(base_url: str, healthy: bool) -> str:
    base = base_url.rstrip("/")
    return base if healthy else f"{base}/fail"


def send_heartbeat(client: httpx2.Client, base_url: str, healthy: bool) -> bool:
    """ping 外部 heartbeat 服務；失敗記 WARNING 回 False，不影響檢查。"""
    # NOTE: log 不印 URL 與例外內容（可能含 URL）：URL 含 check 的 UUID，拿到就能偽造 ping
    try:
        resp = client.get(heartbeat_target(base_url, healthy))
    except httpx2.HTTPError as e:
        log.warning("heartbeat ping failed: %s", type(e).__name__)
        return False
    if not resp.is_success:
        log.warning("heartbeat ping returned %d", resp.status_code)
        return False
    return True


def run_once(
    connect: httpx2.Client,
    engine: Engine,
    heartbeat: httpx2.Client | None,
    connector_watch: ConnectorWatch,
    slot_watch: SlotWatch,
    settings: CdcWatchdogSettings,
    now: float,
    *,
    clickhouse: ClickHouseClient | None = None,
    freshness_watch: FreshnessWatch | None = None,
    wall_now: datetime | None = None,
) -> None:
    """一輪檢查：connector → slot → 資料新鮮度 → heartbeat；heartbeat 為 None 時不送。"""
    check_connector(connect, settings.connector_name, connector_watch, now)
    check_slot(
        engine,
        settings.slot_name,
        slot_watch,
        now,
        statement_timeout_ms=int(settings.request_timeout_s * 1000),
    )
    if clickhouse is not None and freshness_watch is not None:
        check_freshness(clickhouse, freshness_watch, wall_now or datetime.now(UTC))
    if heartbeat is not None and settings.heartbeat_url:
        healthy = is_cdc_healthy(connector_watch, slot_watch, freshness_watch)
        send_heartbeat(heartbeat, settings.heartbeat_url, healthy)


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("cdc-watchdog")
    settings = CdcWatchdogSettings()
    timeout_s = settings.request_timeout_s
    # NOTE: make_engine 不設連線逾時；PG 卡住時要讓這一輪結束，heartbeat 停了外部才會發現
    engine = create_engine(
        get_postgres_settings().url(),
        pool_size=1,
        pool_pre_ping=True,
        connect_args={"connect_timeout": max(1, int(timeout_s))},
    )
    connect = httpx2.Client(base_url=ConnectSettings().url, timeout=timeout_s)
    heartbeat = httpx2.Client(timeout=timeout_s) if settings.heartbeat_url else None
    connector_watch = ConnectorWatch(
        settings.restart_backoff_initial_s, settings.restart_backoff_max_s
    )
    slot_watch = SlotWatch(settings.slot_inactive_alert_s, settings.slot_lag_alert_bytes)
    clickhouse = ClickHouseClient(ClickHouseSettings(), timeout_s=timeout_s)
    freshness_watch = FreshnessWatch(settings.stale_alert_s, datetime.now(UTC))

    def tick() -> None:
        try:
            run_once(
                connect,
                engine,
                heartbeat,
                connector_watch,
                slot_watch,
                settings,
                time.monotonic(),
                clickhouse=clickhouse,
                freshness_watch=freshness_watch,
            )
        except Exception:
            # 不讓單輪的意外錯誤停掉 watchdog；這一輪不送 heartbeat，持續發生時外部服務會通知
            log.exception("watchdog round failed")

    scheduler = BlockingScheduler(
        timezone=UTC,
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
    )
    scheduler.add_job(
        tick, "interval", seconds=settings.interval_s, id="watch", next_run_time=datetime.now(UTC)
    )
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: scheduler.shutdown(wait=False))
    log.info(
        "cdc-watchdog watching connector %s and slot %s every %.0fs (heartbeat %s)",
        settings.connector_name,
        settings.slot_name,
        settings.interval_s,
        "on" if heartbeat else "off",
    )
    try:
        scheduler.start()
    finally:
        log.info("cdc-watchdog stopping")
        connect.close()
        if heartbeat is not None:
            heartbeat.close()
        clickhouse.close()
        engine.dispose()


if __name__ == "__main__":
    main()

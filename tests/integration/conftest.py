"""整合測試連 compose 的 kafka／postgres／clickhouse（開發規格 7.26），不再啟動容器。

連線由 IT_* 環境變數提供；缺任何一個就中止（不 skip，否則 CI 會假綠）。
平行執行（pytest-xdist）時，全域重置只做一次，PG 與 ClickHouse 各 worker 用自己的 database。
"""

import os
import time

import pytest
from confluent_kafka.admin import AdminClient, NewTopic
from sqlalchemy import create_engine, text

from radar.common.clickhouse import ClickHouseClient
from radar.common.kafka import names
from radar.common.kafka.config import admin_config
from radar.common.settings import (
    ClickHouseSettings,
    KafkaSettings,
    PostgresSettings,
    get_kafka_settings,
    get_postgres_settings,
)
from tests.helpers.clickhouse import (
    apply_migrations,
    create_worker_database,
    drop_databases,
    is_current,
    is_test_host,
    it_clickhouse_settings,
    reset_keeping_radar,
    truncate_data_tables,
    worker_database,
)
from tests.integration._xdist import run_once, worker_id

REQUIRED_ENV = (
    "IT_KAFKA_BOOTSTRAP",
    "IT_POSTGRES_HOST",
    "IT_POSTGRES_PORT",
    "IT_CLICKHOUSE_URL",
    "IT_GRAFANA_URL",
)
USAGE = (
    "整合測試需要 compose 的測試服務，請在主目錄執行：\n"
    "  docker compose --env-file .env -f .worktrees/<task_id>/compose.yaml run --rm test\n"
    "CI 由 workflow 設定 IT_* 後直接在 runner 上跑（見 docs/development-spec.md 7.26）"
)
# NOTE: 測試專用帳密與 DB 名稱，與 compose.yaml 的 postgres 服務一致；不讀 POSTGRES_*（開發 DB）
PG_USER = "radar"
PG_PASSWORD = "it"
PG_DB = "radar_it"
# 每個 worker 一個 DB：radar_it_<worker>；重置與重建前以這個前綴防呆
PG_WORKER_PREFIX = "radar_it_"
# NOTE: 與 compose.yaml 的 kafka CLUSTER_ID 一致，且刻意不同於 .env.example 的開發環境
KAFKA_TEST_CLUSTER_ID = "hw222Z37TDqnGKEUUPeTpA"
# 這四個 topic 由 ClickHouse 的 Kafka engine 表訂閱，migration 前要先存在
CLICKHOUSE_TOPICS = (names.LABELS, names.PREDICTIONS, names.PREDICTIONS_SHADOW, names.ALERTS)
RESET_TIMEOUT_S = 60.0
# 被刪掉的 Kafka engine consumer 不一定會離開 group，broker 等 session 逾時（預設 45 秒）才踢掉
GROUP_LEAVE_TIMEOUT_S = 120.0
CLICKHOUSE_GROUP_PREFIX = "clickhouse-"


def _wait_until(done, what: str, timeout_s: float = RESET_TIMEOUT_S) -> None:
    deadline = time.monotonic() + timeout_s
    while not done():
        if time.monotonic() > deadline:
            raise TimeoutError(what)
        time.sleep(0.3)


def _user_topics(admin: AdminClient) -> list[str]:
    return [t for t in admin.list_topics(timeout=30).topics if not t.startswith("__")]


def check_kafka_target(
    settings: KafkaSettings, expected_cluster_id: str = KAFKA_TEST_CLUSTER_ID
) -> AdminClient:
    """主機在允許清單且 cluster_id 相符才回傳 admin；否則 pytest.exit，什麼都不動。"""
    for server in settings.bootstrap_servers.split(","):
        host = server.strip().rsplit(":", 1)[0]
        if not is_test_host(host):
            pytest.exit(f"拒絕重置 Kafka {host!r}：只能是測試服務或本機", returncode=2)
    admin = AdminClient(admin_config(settings))
    # NOTE: localhost:9092 可能是開發 Kafka（主機名稱擋不住），cluster_id 才分得出來
    cluster_id = admin.list_topics(timeout=30).cluster_id
    if cluster_id != expected_cluster_id:
        pytest.exit(
            f"拒絕重置 Kafka：cluster_id {cluster_id!r} 不是測試服務的 {expected_cluster_id!r}",
            returncode=2,
        )
    return admin


def reset_kafka(
    settings: KafkaSettings,
    expected_cluster_id: str = KAFKA_TEST_CLUSTER_ID,
    keep: tuple[str, ...] = (),
) -> None:
    admin = check_kafka_target(settings, expected_cluster_id)
    doomed = [t for t in _user_topics(admin) if t not in keep]
    if doomed:
        for f in admin.delete_topics(doomed).values():
            f.result(30)
        _wait_until(lambda: not set(doomed) & set(_user_topics(admin)), "kafka topics not deleted")
    missing = [t for t in CLICKHOUSE_TOPICS if t not in _user_topics(admin)]
    if not missing:
        return
    futures = admin.create_topics(
        [NewTopic(t, num_partitions=1, replication_factor=1) for t in missing]
    )
    for f in futures.values():
        f.result(30)


def _pg_admin(url: str):
    """連到 radar_it（compose 建立的 DB）做 DB 層級的管理；不是它就拒絕。"""
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    conn = engine.connect()
    db = conn.execute(text("SELECT current_database()")).scalar_one()
    if db != PG_DB:
        conn.close()
        engine.dispose()
        pytest.exit(f"拒絕重置資料庫 {db!r}：整合測試只能用 {PG_DB!r}", returncode=2)
    return engine, conn


def wait_clickhouse_groups_empty(settings: KafkaSettings) -> None:
    """舊的 consumer 還留在 group 裡時，新的 Kafka engine 表要等它逾時才分到 partition。"""
    admin = AdminClient(admin_config(settings))

    def empty() -> bool:
        listed = admin.list_consumer_groups().result().valid
        ids = [g.group_id for g in listed if g.group_id.startswith(CLICKHOUSE_GROUP_PREFIX)]
        if not ids:
            return True
        return all(not f.result().members for f in admin.describe_consumer_groups(ids).values())

    _wait_until(empty, "clickhouse consumer groups still have members", GROUP_LEAVE_TIMEOUT_S)


def reset_postgres(url: str) -> None:
    """全域重置：刪掉上次留下的 worker DB 與沒人用的 replication slot。"""
    engine, conn = _pg_admin(url)
    try:
        # NOTE: 有 slot 的 DB 刪不掉，所以先刪 slot
        slots = conn.execute(
            text("SELECT slot_name FROM pg_replication_slots WHERE NOT active")
        ).all()
        for (slot,) in slots:
            conn.execute(text("SELECT pg_drop_replication_slot(:s)"), {"s": slot})
        like = PG_WORKER_PREFIX.replace("_", r"\_") + "%"
        leftovers = conn.execute(
            text("SELECT datname FROM pg_database WHERE datname LIKE :p"), {"p": like}
        ).all()
        for (name,) in leftovers:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    finally:
        conn.close()
        engine.dispose()


def create_worker_postgres(url: str, worker: str) -> None:
    engine, conn = _pg_admin(url)
    name = f"{PG_WORKER_PREFIX}{worker}"
    try:
        if not name.replace("_", "").isalnum():
            pytest.exit(f"worker id {worker!r} 不能當 DB 名稱", returncode=2)
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    finally:
        conn.close()
        engine.dispose()


def _pg_url(db: str = PG_DB) -> str:
    host, port = os.environ["IT_POSTGRES_HOST"], os.environ["IT_POSTGRES_PORT"]
    return f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{host}:{port}/{db}"


def _reset_global() -> None:
    """整個測試只做一次；Kafka 目標確認後才動任何東西。

    NOTE: 全部重建時順序是 ClickHouse（停掉舊的 consumer）→ Kafka → 重建 ClickHouse。
    """
    ch = it_clickhouse_settings()
    kafka = KafkaSettings(bootstrap_servers=os.environ["IT_KAFKA_BOOTSTRAP"], client_id="it")
    check_kafka_target(kafka)
    reset_postgres(_pg_url())
    if is_current(ch):
        reset_keeping_radar(ch)
        reset_kafka(kafka, keep=CLICKHOUSE_TOPICS)
        return
    drop_databases(ch)
    reset_kafka(kafka)
    wait_clickhouse_groups_empty(kafka)
    apply_migrations(ch)


@pytest.fixture(scope="session")
def worker() -> str:
    return worker_id()


@pytest.fixture(scope="session", autouse=True)
def it_services(worker: str) -> None:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        pytest.exit(f"缺少環境變數 {', '.join(missing)}\n{USAGE}", returncode=2)
    run_once("global", _reset_global)
    create_worker_postgres(_pg_url(), worker)
    ch = it_clickhouse_settings(db=worker_database(worker))
    create_worker_database(ch)
    apply_migrations(ch, kafka=False)


@pytest.fixture(scope="session")
def postgres_url(worker: str) -> str:
    return _pg_url(f"{PG_WORKER_PREFIX}{worker}")


@pytest.fixture(scope="session")
def wait_until():
    """條件成立才繼續（逾時丟 TimeoutError）；取代固定 sleep，等 broker metadata 傳播用。"""
    return _wait_until


@pytest.fixture(scope="session")
def kafka_settings() -> KafkaSettings:
    return KafkaSettings(bootstrap_servers=os.environ["IT_KAFKA_BOOTSTRAP"], client_id="it")


@pytest.fixture(scope="session")
def clickhouse_settings() -> ClickHouseSettings:
    """共用的 radar database（有 Kafka engine 表）；只給依賴 Kafka 接入的測試。"""
    return it_clickhouse_settings()


@pytest.fixture(scope="session")
def worker_clickhouse_settings(worker: str) -> ClickHouseSettings:
    return it_clickhouse_settings(db=worker_database(worker))


@pytest.fixture(scope="module")
def clickhouse(worker_clickhouse_settings):
    """worker 專用 database（沒有 Kafka engine 表）的 client；模組開始時清空資料表。"""
    client = ClickHouseClient(worker_clickhouse_settings)
    truncate_data_tables(client, worker_clickhouse_settings.db)
    yield client
    client.close()


@pytest.fixture(scope="module")
def shared_clickhouse(clickhouse_settings):
    """radar database 的 client；Kafka engine 表保留，只清資料表。須標 xdist_group。"""
    client = ClickHouseClient(clickhouse_settings)
    truncate_data_tables(client)
    yield client
    client.close()


@pytest.fixture
def postgres_env(monkeypatch, worker):
    """把連線資訊放進 POSTGRES_* 環境變數，供 alembic env.py 等讀取。"""
    env = {
        "POSTGRES_HOST": os.environ["IT_POSTGRES_HOST"],
        "POSTGRES_PORT": os.environ["IT_POSTGRES_PORT"],
        "POSTGRES_DB": f"{PG_WORKER_PREFIX}{worker}",
        "POSTGRES_USER": PG_USER,
        "POSTGRES_PASSWORD": PG_PASSWORD,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_postgres_settings.cache_clear()
    get_kafka_settings.cache_clear()
    yield PostgresSettings()
    get_postgres_settings.cache_clear()

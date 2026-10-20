"""整合測試連 compose 的 kafka／postgres／clickhouse（開發規格 7.26），不再啟動容器。

連線由 IT_* 環境變數提供；缺任何一個就中止（不 skip，否則 CI 會假綠）。
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
    drop_databases,
    is_test_host,
    it_clickhouse_settings,
    truncate_data_tables,
)

REQUIRED_ENV = ("IT_KAFKA_BOOTSTRAP", "IT_POSTGRES_HOST", "IT_POSTGRES_PORT", "IT_CLICKHOUSE_URL")
USAGE = (
    "整合測試需要 compose 的測試服務，請在主目錄執行：\n"
    "  docker compose --env-file .env -f .worktrees/<task_id>/compose.yaml run --rm test\n"
    "CI 由 workflow 設定 IT_* 後直接在 runner 上跑（見 docs/development-spec.md 7.26）"
)
# NOTE: 測試專用帳密與 DB 名稱，與 compose.yaml 的 postgres 服務一致；不讀 POSTGRES_*（開發 DB）
PG_USER = "radar"
PG_PASSWORD = "it"
PG_DB = "radar_it"
# 這三個 topic 由 ClickHouse 的 Kafka engine 表訂閱，migration 前要先存在
CLICKHOUSE_TOPICS = (names.LABELS, names.PREDICTIONS, names.ALERTS)
RESET_TIMEOUT_S = 60.0


def _wait_until(done, what: str) -> None:
    deadline = time.monotonic() + RESET_TIMEOUT_S
    while not done():
        if time.monotonic() > deadline:
            raise TimeoutError(what)
        time.sleep(0.3)


def _user_topics(admin: AdminClient) -> list[str]:
    return [t for t in admin.list_topics(timeout=30).topics if not t.startswith("__")]


def reset_kafka(settings: KafkaSettings) -> None:
    for server in settings.bootstrap_servers.split(","):
        host = server.strip().rsplit(":", 1)[0]
        if not is_test_host(host):
            pytest.exit(f"拒絕重置 Kafka {host!r}：只能是測試服務或本機", returncode=2)
    admin = AdminClient(admin_config(settings))
    existing = _user_topics(admin)
    if existing:
        for f in admin.delete_topics(existing).values():
            f.result(30)
        _wait_until(lambda: not _user_topics(admin), "kafka topics not deleted")
    futures = admin.create_topics(
        [NewTopic(t, num_partitions=1, replication_factor=1) for t in CLICKHOUSE_TOPICS]
    )
    for f in futures.values():
        f.result(30)


def reset_postgres(url: str) -> None:
    engine = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as conn:
            db = conn.execute(text("SELECT current_database()")).scalar_one()
            if db != PG_DB:
                pytest.exit(f"拒絕重置資料庫 {db!r}：整合測試只能用 {PG_DB!r}", returncode=2)
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            for (pub,) in conn.execute(text("SELECT pubname FROM pg_publication")).all():
                conn.execute(text(f'DROP PUBLICATION "{pub}"'))
            slots = conn.execute(
                text("SELECT slot_name FROM pg_replication_slots WHERE NOT active")
            ).all()
            for (slot,) in slots:
                conn.execute(text("SELECT pg_drop_replication_slot(:s)"), {"s": slot})
    finally:
        engine.dispose()


def _pg_url() -> str:
    host, port = os.environ["IT_POSTGRES_HOST"], os.environ["IT_POSTGRES_PORT"]
    return f"postgresql+psycopg://{PG_USER}:{PG_PASSWORD}@{host}:{port}/{PG_DB}"


@pytest.fixture(scope="session", autouse=True)
def it_services() -> None:
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k)]
    if missing:
        pytest.exit(f"缺少環境變數 {', '.join(missing)}\n{USAGE}", returncode=2)
    # NOTE: 順序是 ClickHouse（停掉舊的 consumer）→ Kafka → 重建 ClickHouse（topic 要先存在）
    ch = it_clickhouse_settings()
    reset_postgres(_pg_url())
    drop_databases(ch)
    reset_kafka(KafkaSettings(bootstrap_servers=os.environ["IT_KAFKA_BOOTSTRAP"], client_id="it"))
    apply_migrations(ch)


@pytest.fixture(scope="session")
def postgres_url() -> str:
    return _pg_url()


@pytest.fixture(scope="session")
def kafka_settings() -> KafkaSettings:
    return KafkaSettings(bootstrap_servers=os.environ["IT_KAFKA_BOOTSTRAP"], client_id="it")


@pytest.fixture(scope="session")
def clickhouse_settings() -> ClickHouseSettings:
    return it_clickhouse_settings()


@pytest.fixture(scope="module")
def clickhouse(clickhouse_settings):
    """radar database 的 client；模組開始時清空資料表（migration 與 Kafka engine 表保留）。"""
    client = ClickHouseClient(clickhouse_settings)
    truncate_data_tables(client)
    yield client
    client.close()


@pytest.fixture
def postgres_env(monkeypatch):
    """把連線資訊放進 POSTGRES_* 環境變數，供 alembic env.py 等讀取。"""
    env = {
        "POSTGRES_HOST": os.environ["IT_POSTGRES_HOST"],
        "POSTGRES_PORT": os.environ["IT_POSTGRES_PORT"],
        "POSTGRES_DB": PG_DB,
        "POSTGRES_USER": PG_USER,
        "POSTGRES_PASSWORD": PG_PASSWORD,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_postgres_settings.cache_clear()
    get_kafka_settings.cache_clear()
    yield PostgresSettings()
    get_postgres_settings.cache_clear()

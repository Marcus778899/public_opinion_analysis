"""整合測試用的 ClickHouse：連 compose 的 clickhouse 服務（IT_CLICKHOUSE_URL），重置與清表。"""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlparse

from pydantic import SecretStr

from radar.common.clickhouse import (
    MIGRATIONS_TABLE,
    ClickHouseClient,
    apply_pending,
    load_migrations,
)
from radar.common.settings import ClickHouseSettings

CH_DIR = Path(__file__).resolve().parents[2] / "infra/clickhouse"
# NOTE: 測試專用帳密，與 compose.yaml 的 clickhouse 服務一致，不是機密
CH_USER = "radar"
CH_PASSWORD = "it"
CH_DB = "radar"
SYSTEM_DATABASES = ("system", "INFORMATION_SCHEMA", "information_schema", "default")
# 不能 TRUNCATE 的引擎：Kafka 表沒有資料，MV 的資料在目標表
NON_DATA_ENGINES = ("Kafka", "MaterializedView", "View")


# 重置前的防呆：只允許 compose 的服務別名與本機（CI 的 runner），不是就拒絕
TEST_HOSTS = frozenset({"kafka", "kafka_1", "kafka_2", "kafka_3", "postgres", "clickhouse"})
TEST_HOSTS |= {"localhost", "127.0.0.1"}


def is_test_host(host: str) -> bool:
    return host in TEST_HOSTS


def assert_test_clickhouse(settings: ClickHouseSettings) -> None:
    host = urlparse(settings.url).hostname or ""
    if not is_test_host(host) or settings.db != CH_DB:
        raise PermissionError(
            f"拒絕重置 ClickHouse {host!r} database {settings.db!r}：只能是測試服務的 {CH_DB!r}"
        )


def it_clickhouse_settings(url: str | None = None) -> ClickHouseSettings:
    return ClickHouseSettings(
        url=url or os.environ["IT_CLICKHOUSE_URL"],
        db=CH_DB,
        user=CH_USER,
        password=SecretStr(CH_PASSWORD),
    )


def drop_databases(settings: ClickHouseSettings) -> None:
    """刪掉所有非系統 database（連同 Kafka engine 的 consumer），再建空的設定 database。"""
    assert_test_clickhouse(settings)
    # NOTE: radar 被刪掉後帶 database=radar 的請求會被拒絕，所以管理操作連 default
    client = ClickHouseClient(settings.model_copy(update={"db": "default"}))
    try:
        names = client.execute("SELECT name FROM system.databases FORMAT TSV").splitlines()
        for name in names:
            if name not in SYSTEM_DATABASES:
                client.execute(f"DROP DATABASE IF EXISTS `{name}` SYNC")
        client.execute(f"CREATE DATABASE `{settings.db}`")
    finally:
        client.close()


def apply_migrations(settings: ClickHouseSettings) -> None:
    """Kafka topic 要已建好，否則 Kafka engine 表訂閱不到。"""
    client = ClickHouseClient(settings)
    try:
        apply_pending(client, load_migrations(CH_DIR / "migrations"))
    finally:
        client.close()


def truncate_data_tables(client: ClickHouseClient, db: str = CH_DB) -> None:
    engines = ", ".join(f"'{e}'" for e in NON_DATA_ENGINES)
    rows = client.execute(
        "SELECT name FROM system.tables "
        f"WHERE database = '{db}' AND engine NOT IN ({engines}) "
        f"AND name != '{MIGRATIONS_TABLE}' FORMAT TSV"
    )
    for name in rows.splitlines():
        client.execute(f"TRUNCATE TABLE `{name}`")


def drop_queue_tables(client: ClickHouseClient, db: str) -> None:
    """同 consumer group 的 Kafka engine 表只能有一組，另建的 database 套完 migration 要刪。"""
    rows = client.execute(
        f"SELECT name FROM system.tables WHERE database = '{db}' AND engine = 'Kafka' FORMAT TSV"
    )
    for name in rows.splitlines():
        client.execute(f"DROP TABLE `{name}` SYNC")


@contextmanager
def clickhouse_client() -> Iterator[ClickHouseClient]:
    """radar database 已由 session 重置套好 migration；表內容由各測試自己清。"""
    client = ClickHouseClient(it_clickhouse_settings())
    try:
        yield client
    finally:
        client.close()

import pytest
from testcontainers.community.kafka import KafkaContainer
from testcontainers.community.postgres import PostgresContainer

from radar.common.settings import (
    KafkaSettings,
    PostgresSettings,
    get_kafka_settings,
    get_postgres_settings,
)


@pytest.fixture(scope="session")
def kafka_settings():
    # NOTE: 整合測試只驗證程式邏輯，單節點即可；3 節點行為由 make up 驗證
    with KafkaContainer().with_kraft() as kafka:
        yield KafkaSettings(bootstrap_servers=kafka.get_bootstrap_server(), client_id="it")


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:17", driver="psycopg") as pg:
        yield pg


@pytest.fixture
def postgres_env(postgres_container, monkeypatch):
    """把容器連線資訊放進 POSTGRES_* 環境變數，供 alembic env.py 等讀取。"""
    pg = postgres_container
    env = {
        "POSTGRES_HOST": pg.get_container_host_ip(),
        "POSTGRES_PORT": str(pg.get_exposed_port(5432)),
        "POSTGRES_DB": pg.dbname,
        "POSTGRES_USER": pg.username,
        "POSTGRES_PASSWORD": pg.password,
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_postgres_settings.cache_clear()
    get_kafka_settings.cache_clear()
    yield PostgresSettings()
    get_postgres_settings.cache_clear()

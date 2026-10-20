"""整合測試用的 ClickHouse 容器：套用 infra/clickhouse 的設定與 migration。"""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx2
from pydantic import SecretStr
from testcontainers.core.container import DockerContainer

from radar.common.clickhouse import ClickHouseClient, apply_pending, load_migrations
from radar.common.settings import ClickHouseSettings

CH_DIR = Path(__file__).resolve().parents[2] / "infra/clickhouse"


@contextmanager
def clickhouse_client() -> Iterator[ClickHouseClient]:
    """Kafka engine 表連不上 broker 只會記 log，不影響直接寫入的測試資料。"""
    container = (
        DockerContainer("clickhouse/clickhouse-server:26.8")
        .with_env("CLICKHOUSE_USER", "radar")
        .with_env("CLICKHOUSE_PASSWORD", "it")
        .with_env("CLICKHOUSE_DB", "radar")
        .with_volume_mapping(
            str(CH_DIR / "config.d/named_collections.xml"),
            "/etc/clickhouse-server/config.d/named_collections.xml",
        )
        .with_volume_mapping(
            str(CH_DIR / "users.d/radar.xml"), "/etc/clickhouse-server/users.d/radar.xml"
        )
        .with_exposed_ports(8123)
    )
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8123)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx2.get(f"{url}/ping").status_code == 200:
                    break
            except httpx2.TransportError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("clickhouse not ready")
            time.sleep(1)
        client = ClickHouseClient(
            ClickHouseSettings(url=url, db="radar", user="radar", password=SecretStr("it"))
        )
        apply_pending(client, load_migrations(CH_DIR / "migrations"))
        yield client
        client.close()

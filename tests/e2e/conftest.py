"""端到端測試：需先 make e2e-up（整套 compose 加上假 PTT；init 會建表、topic 與 connector）。"""

import time
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx2
import pytest
from sqlalchemy import text

from radar.common.clickhouse import ClickHouseClient, ClickHouseError
from radar.common.db.session import make_engine
from radar.common.settings import ClickHouseSettings, PostgresSettings

E2E_DIR = Path(__file__).resolve().parent
API_URL = "http://localhost:8000"
FAKE_PTT_URL = "http://localhost:8081"


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # NOTE: 這個 hook 會收到所有測試，只標記本目錄下的，讓一般 pytest 與 CI 排除它們
    for item in items:
        if E2E_DIR in Path(item.path).parents:
            item.add_marker(pytest.mark.e2e)


def wait_until[T](fn: Callable[[], T], *, timeout_s: float = 90, interval_s: float = 2) -> T:
    """重複呼叫 fn 直到回傳 truthy；逾時拋 AssertionError。"""
    deadline = time.monotonic() + timeout_s
    while True:
        result = fn()
        if result:
            return result
        if time.monotonic() > deadline:
            raise AssertionError(f"condition not met within {timeout_s}s")
        time.sleep(interval_s)


@pytest.fixture(scope="session")
def api():
    client = httpx2.Client(base_url=API_URL, timeout=10)
    try:
        client.get("/boards").raise_for_status()
    except httpx2.HTTPError:
        pytest.skip("API 未啟動，請先 make e2e-up && make migrate topics")
    yield client
    client.close()


@pytest.fixture(scope="session")
def fake_ptt():
    client = httpx2.Client(base_url=FAKE_PTT_URL, timeout=10)
    try:
        client.get("/bbs/E2E/index.html").raise_for_status()
    except httpx2.HTTPError:
        pytest.skip("假 PTT 伺服器未啟動，請先 make e2e-up")
    yield client
    client.close()


@pytest.fixture(scope="session")
def db():
    engine = make_engine(PostgresSettings())
    yield engine
    engine.dispose()


@pytest.fixture
def board(api):
    """每個測試用自己的看板，避免互相干擾；結束後停用。"""
    name = f"E2E{uuid.uuid4().hex[:6]}"
    api.post("/boards", json={"board": name, "interval_sec": 30}).raise_for_status()
    yield name
    api.patch(f"/boards/{name}", json={"enabled": False})


def post_row(db, post_id: str):
    with db.connect() as conn:
        return conn.execute(
            text("SELECT push_count, boo_count, is_deleted FROM posts WHERE post_id = :id"),
            {"id": post_id},
        ).one_or_none()


@pytest.fixture(scope="session")
def clickhouse():
    client = ClickHouseClient(ClickHouseSettings())
    try:
        client.execute("SELECT 1")
    except (ClickHouseError, httpx2.HTTPError):
        pytest.skip("ClickHouse 未啟動，請先 make e2e-up")
    yield client
    client.close()


def clickhouse_rows(clickhouse, sql: str) -> list[list[str]]:
    return [line.split("\t") for line in clickhouse.execute(f"{sql} FORMAT TSV").splitlines()]

"""驗收 dashboard-grafana-infra（開發規格 7.25「test_grafana_infra.py 要驗的」）。

連 compose 的 grafana（IT_GRAFANA_URL）與 clickhouse（IT_CLICKHOUSE_URL）。
`run --rm test` 下 Grafana 只接 internal network，所以通過即代表離線啟動可用；
CI 的 Grafana 有對外網路，不構成離線證據。測試帳密與 compose.yaml 一致，不讀 .env。
"""

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ID = "grafana-clickhouse-datasource"
DATASOURCE_UID = "radar-clickhouse"
GRAFANA_USER = "admin"
GRAFANA_PASSWORD = os.environ.get("GRAFANA_ADMIN_PASSWORD", "it")
RO_USER = os.environ.get("CLICKHOUSE_GRAFANA_USER", "grafana")
RO_PASSWORD = os.environ.get("CLICKHOUSE_GRAFANA_PASSWORD", "it")
ADMIN_USER, ADMIN_PASSWORD = "radar", "it"
RADAR_DB = "radar"
READY_TIMEOUT_S = 90.0


def _expected(var: str) -> str:
    """版本取自環境變數；CI 的 runner 沒有就讀 .env.example（CI 以它複製成 .env）。"""
    value = os.environ.get(var)
    if value:
        return value
    m = re.search(rf"^{var}=(.*)$", (ROOT / ".env.example").read_text(), re.M)
    assert m, f"{var} 未設定"
    return m.group(1).strip().strip('"')


def _grafana_url() -> str:
    url = os.environ.get("IT_GRAFANA_URL")
    if not url:
        pytest.fail("缺少 IT_GRAFANA_URL（compose test 服務或 CI 要設定）", pytrace=False)
    return url.rstrip("/")


def _get(url: str, auth: tuple[str, str] | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        req.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _ch(
    sql: str, user: str = RO_USER, password: str = RO_PASSWORD, database: str | None = RADAR_DB
) -> tuple[int, str]:
    """用 POST 送（GET 在 ClickHouse HTTP 預設是 readonly，會讓寫入類測試因為錯的原因失敗）。"""
    base = os.environ["IT_CLICKHOUSE_URL"].rstrip("/")
    url = f"{base}/" + (f"?database={database}" if database else "")
    req = urllib.request.Request(
        url,
        data=sql.encode(),
        method="POST",
        headers={"X-ClickHouse-User": user, "X-ClickHouse-Key": password},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode().strip()


def _admin(sql: str, database: str | None = RADAR_DB) -> None:
    status, body = _ch(sql, ADMIN_USER, ADMIN_PASSWORD, database)
    assert status == 200, body


def _wait_health(url: str) -> dict:
    deadline = time.monotonic() + READY_TIMEOUT_S
    last = ""
    while time.monotonic() < deadline:
        try:
            status, body = _get(f"{url}/api/health")
            if status == 200:
                return json.loads(body)
            last = f"{status} {body}"
        except (urllib.error.URLError, OSError) as e:
            last = repr(e)
        time.sleep(1)
    pytest.fail(f"Grafana 在 {READY_TIMEOUT_S} 秒內未就緒：{last}", pytrace=False)


def _limits() -> dict[str, str]:
    root = ET.fromstring((ROOT / "infra/clickhouse/users.d/grafana.xml").read_text())
    out = {}
    for tag in ("max_execution_time", "max_memory_usage"):
        el = next(root.iter(tag), None)
        assert el is not None and (el.text or "").strip(), f"grafana.xml 沒有 {tag}"
        out[tag] = el.text.strip()
    return out


@pytest.fixture(scope="module")
def grafana() -> str:
    url = _grafana_url()
    _wait_health(url)
    return url


@pytest.fixture(autouse=True)
def _readonly_user_exists(request: pytest.FixtureRequest) -> None:
    """拒絕類的測試先確認帳號能登入，否則「帳號不存在」也會讓它們假通過。"""
    name = request.node.name
    if name.startswith(("test_readonly_user_cannot", "test_readonly_user_sees_no")):
        status, body = _ch("SELECT 1")
        assert (status, body) == (200, "1"), f"唯讀帳號無法登入：{body}"


@pytest.fixture
def other_database():
    name = f"radar_other_{uuid.uuid4().hex[:8]}"
    _admin(f"CREATE DATABASE `{name}`", database=None)
    _admin(f"CREATE TABLE `{name}`.t (x UInt8) ENGINE = Memory", database=None)
    _admin(f"INSERT INTO `{name}`.t VALUES (1)", database=None)
    yield name
    _admin(f"DROP DATABASE IF EXISTS `{name}` SYNC", database=None)


# ---- 相容性、離線啟動 ----


def test_grafana_health_reports_database_ok_and_pinned_version(grafana: str) -> None:
    health = _wait_health(grafana)
    assert health["database"] == "ok"
    assert health["version"].startswith(_expected("GRAFANA_VERSION"))


def test_clickhouse_plugin_is_loaded_with_pinned_version(grafana: str) -> None:
    status, body = _get(
        f"{grafana}/api/plugins/{PLUGIN_ID}/settings", (GRAFANA_USER, GRAFANA_PASSWORD)
    )
    assert status == 200, body
    info = json.loads(body)
    assert info["id"] == PLUGIN_ID
    assert info["info"]["version"] == _expected("GRAFANA_CLICKHOUSE_PLUGIN_VERSION")


def test_provisioned_datasource_health_check_succeeds(grafana: str) -> None:
    status, body = _get(
        f"{grafana}/api/datasources/uid/{DATASOURCE_UID}/health", (GRAFANA_USER, GRAFANA_PASSWORD)
    )
    assert status == 200, body
    assert json.loads(body)["status"].upper() == "OK", body


def test_provisioned_datasource_has_fixed_uid_and_plugin_type(grafana: str) -> None:
    status, body = _get(
        f"{grafana}/api/datasources/uid/{DATASOURCE_UID}", (GRAFANA_USER, GRAFANA_PASSWORD)
    )
    assert status == 200, body
    assert json.loads(body)["type"] == PLUGIN_ID


def test_grafana_rejects_anonymous_and_wrong_password(grafana: str) -> None:
    assert _get(f"{grafana}/api/datasources")[0] in (401, 403)
    assert _get(f"{grafana}/api/datasources", (GRAFANA_USER, "wrong-password"))[0] == 401
    assert _get(f"{grafana}/api/datasources", (GRAFANA_USER, "admin"))[0] == 401


# ---- 唯讀帳號 ----


def test_readonly_user_can_select_radar_tables() -> None:
    for table in ("posts_latest", "comments_latest", "alerts", "predictions"):
        status, body = _ch(f"SELECT count() FROM {RADAR_DB}.{table}")
        assert status == 200, f"{table}: {body}"
        assert body.isdigit()


def test_readonly_user_can_select_a_radar_view() -> None:
    view = f"v_acceptance_{uuid.uuid4().hex[:8]}"
    _admin(f"CREATE VIEW {RADAR_DB}.{view} AS SELECT 1 AS x")
    try:
        assert _ch(f"SELECT x FROM {RADAR_DB}.{view}") == (200, "1")
    finally:
        _admin(f"DROP VIEW IF EXISTS {RADAR_DB}.{view}")


def test_readonly_user_cannot_insert() -> None:
    before = _ch(f"SELECT count() FROM {RADAR_DB}.alerts", "radar", "it")[1]
    status, body = _ch(f"INSERT INTO {RADAR_DB}.alerts SELECT * FROM {RADAR_DB}.alerts LIMIT 0")
    assert status != 200, body
    assert _ch(f"SELECT count() FROM {RADAR_DB}.alerts", "radar", "it")[1] == before


def test_readonly_user_cannot_create_table() -> None:
    name = f"t_acceptance_{uuid.uuid4().hex[:8]}"
    status, body = _ch(f"CREATE TABLE {RADAR_DB}.{name} (x UInt8) ENGINE = Memory")
    assert status != 200, body
    assert _ch(f"EXISTS TABLE {RADAR_DB}.{name}", ADMIN_USER, ADMIN_PASSWORD)[1] == "0"


def test_readonly_user_cannot_drop_table() -> None:
    status, body = _ch(f"DROP TABLE {RADAR_DB}.posts_latest")
    assert status != 200, body
    assert _ch(f"EXISTS TABLE {RADAR_DB}.posts_latest", ADMIN_USER, ADMIN_PASSWORD)[1] == "1"


def test_readonly_user_cannot_create_database() -> None:
    name = f"radar_evil_{uuid.uuid4().hex[:8]}"
    status, body = _ch(f"CREATE DATABASE {name}", database=None)
    assert status != 200, body
    assert name not in _ch("SHOW DATABASES", ADMIN_USER, ADMIN_PASSWORD, None)[1]


def test_readonly_user_cannot_turn_readonly_off() -> None:
    status, body = _ch("SET readonly = 0")
    assert status != 200, body
    status, body = _ch(f"SELECT count() FROM {RADAR_DB}.posts_latest SETTINGS readonly = 0")
    assert status != 200, body
    status, body = _ch("SELECT 1 SETTINGS max_execution_time = 0")
    assert status != 200, body


def test_readonly_user_cannot_query_other_databases(other_database: str) -> None:
    status, body = _ch(f"SELECT x FROM `{other_database}`.t")
    assert status != 200, body
    assert _ch(f"SELECT x FROM `{other_database}`.t", ADMIN_USER, ADMIN_PASSWORD)[1] == "1"


def test_readonly_user_cannot_read_xdist_worker_database(worker: str) -> None:
    status, body = _ch(f"SELECT count() FROM {RADAR_DB}_{worker}.posts_latest")
    assert status != 200, body


def test_readonly_user_sees_no_named_collections() -> None:
    admin_count = _ch("SELECT count() FROM system.named_collections", ADMIN_USER, ADMIN_PASSWORD)
    assert admin_count[0] == 200 and int(admin_count[1]) > 0, (
        "前提：管理帳號看得到 named collection"
    )
    status, body = _ch("SELECT count() FROM system.named_collections")
    assert status != 200 or body == "0", body
    status, body = _ch("SELECT name FROM system.named_collections")
    assert status != 200 or body == "", body


def test_readonly_user_cannot_manage_named_collections() -> None:
    status, body = _ch("CREATE NAMED COLLECTION nc_acceptance AS a = 1")
    assert status != 200, body


@pytest.mark.parametrize("setting", ["max_execution_time", "max_memory_usage"])
def test_readonly_user_limits_equal_configured_values(setting: str) -> None:
    status, body = _ch(f"SELECT getSetting('{setting}')")
    assert status == 200, body
    assert float(body) == float(_limits()[setting]) > 0


# ---- 設定載入（from_env）----


def test_readonly_user_login_succeeds_with_configured_password() -> None:
    assert _ch("SELECT 1") == (200, "1")


@pytest.mark.parametrize("password", ["wrong-password", "", "change-me"])
def test_readonly_user_login_fails_with_other_password(password: str) -> None:
    assert _ch("SELECT 1") == (200, "1"), "前提：正確密碼可登入"
    status, body = _ch("SELECT 1", RO_USER, password)
    assert status in (401, 403, 500), body
    assert body != "1"

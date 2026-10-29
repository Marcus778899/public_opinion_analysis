"""ClickHouse 唯讀帳號 grafana 的實際權限範圍（開發規格 7.25、docs/security/v0.7.0.md 第 6 節）。

直接用 grafana 帳號打 ClickHouse HTTP，不經 Grafana；帳密與 compose.yaml 一致，不讀 .env。
"""

import os
import urllib.error
import urllib.request

import pytest

pytestmark = pytest.mark.xdist_group("shared_radar_db")

GRAFANA_USER = os.environ.get("CLICKHOUSE_GRAFANA_USER", "grafana")
GRAFANA_PASSWORD = os.environ.get("CLICKHOUSE_GRAFANA_PASSWORD", "it")
ACCESS_DENIED = "ACCESS_DENIED"
READONLY = "READONLY"


def ch(sql: str, user: str = GRAFANA_USER, password: str = GRAFANA_PASSWORD) -> tuple[int, str]:
    base = os.environ["IT_CLICKHOUSE_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/?database=radar",
        data=sql.encode(),
        method="POST",
        headers={"X-ClickHouse-User": user, "X-ClickHouse-Key": password},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode().strip()


def rows(sql: str) -> list[str]:
    status, body = ch(sql)
    assert status == 200, body
    return body.splitlines()


def assert_denied(sql: str, *codes: str) -> None:
    codes = codes or (ACCESS_DENIED,)
    status, body = ch(sql)
    assert status != 200 and any(c in body for c in codes), (
        f"應被拒絕：{sql}\n{status} {body[:300]}"
    )


# ---------- 讀 ----------


def test_grafana_user_can_read_radar_tables() -> None:
    assert rows("SELECT count() FROM radar.posts_latest")[0].isdigit()
    assert rows("SELECT count() FROM radar.predictions")[0].isdigit()


def test_grafana_user_sees_only_radar_database() -> None:
    assert rows("SELECT name FROM system.databases") == ["radar"]
    assert rows("SHOW DATABASES") == ["radar"]


# ---------- 寫 ----------


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO radar.posts_latest (post_id) VALUES ('x')",
        "CREATE TABLE radar.grafana_probe (a Int8) ENGINE = Memory",
        "CREATE DATABASE grafana_probe",
        "DROP TABLE radar.posts_latest",
        "TRUNCATE TABLE radar.posts_latest",
        "ALTER TABLE radar.posts_latest DELETE WHERE 1",
        "OPTIMIZE TABLE radar.posts_latest",
        "SYSTEM FLUSH LOGS",
    ],
)
def test_write_and_ddl_statements_are_rejected_in_readonly_mode(sql: str) -> None:
    assert_denied(sql, READONLY, ACCESS_DENIED)


def test_readonly_setting_cannot_be_lifted_by_query() -> None:
    assert_denied("SET readonly = 0", READONLY)
    assert_denied("SELECT 1 SETTINGS readonly = 0", READONLY)


def test_max_execution_time_cannot_exceed_profile_limit() -> None:
    status, body = ch("SET max_execution_time = 100")
    assert status != 200 and "SETTING_CONSTRAINT_VIOLATION" in body
    assert rows("SELECT getSetting('max_execution_time')") == ["60"]


# ---------- system 資料庫 ----------


def test_system_tables_listing_is_filtered_to_radar_database() -> None:
    assert rows("SELECT DISTINCT database FROM system.tables") == ["radar"]
    assert rows("SELECT DISTINCT database FROM system.columns") == ["radar"]


@pytest.mark.parametrize(
    "table",
    [
        "users", "roles", "grants", "quotas", "settings_profiles", "processes", "query_log",
        "text_log", "trace_log", "part_log", "named_collections", "clusters", "macros",
        "disks", "metrics", "parts", "merges", "mutations", "replicas", "build_options",
        "numbers", "zeros",
    ],
)  # fmt: skip
def test_sensitive_system_tables_are_denied(table: str) -> None:
    assert_denied(f"SELECT * FROM system.{table}")


def test_information_schema_is_denied() -> None:
    assert_denied("SELECT * FROM information_schema.tables")
    assert_denied("SELECT * FROM INFORMATION_SCHEMA.columns")


def test_system_settings_do_not_expose_credentials() -> None:
    values = rows(
        "SELECT value FROM system.settings "
        "WHERE name IN ('s3_access_key_id', 's3_secret_access_key')"
    )
    assert all(v in ("", "\\N") for v in values)


# ---------- table function ----------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM url('http://example.invalid/x', 'CSV', 'a String')",
        "SELECT * FROM remote('127.0.0.1', 'radar.posts_latest')",
        "SELECT * FROM remoteSecure('example.invalid', 'radar.posts_latest')",
        "SELECT * FROM file('x.csv', 'CSV', 'a String')",
        "SELECT file('/etc/passwd')",
        "SELECT * FROM s3('http://example.invalid:9000/bucket/key.csv', 'CSV', 'a String')",
        "SELECT * FROM hdfs('hdfs://example.invalid/x', 'CSV', 'a String')",
        "SELECT * FROM mysql('example.invalid:3306', 'd', 't', 'u', 'p')",
        "SELECT * FROM postgresql('example.invalid:5432', 'd', 't', 'u', 'p')",
        "SELECT * FROM mongodb('example.invalid', 'd', 't', 'u', 'p', 'a Int8')",
        "SELECT * FROM jdbc('a', 'b', 'c')",
        "SELECT * FROM odbc('a', 'b', 'c')",
        "SELECT * FROM azureBlobStorage('x', 'c', 'b', 'CSV')",
        "SELECT * FROM iceberg('http://example.invalid:9000/bucket/key')",
        "SELECT * FROM deltaLake('http://example.invalid:9000/bucket/key')",
        "SELECT * FROM hudi('http://example.invalid:9000/bucket/key')",
    ],
)  # fmt: skip
def test_external_access_table_functions_are_denied(sql: str) -> None:
    assert_denied(sql)


@pytest.mark.parametrize("sql", ["SELECT * FROM executable('ls', 'CSV', 'a String')"])
def test_command_execution_table_functions_are_rejected(sql: str) -> None:
    assert_denied(sql, READONLY)

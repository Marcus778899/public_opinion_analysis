from pathlib import Path

import httpx2
import pytest
from pydantic import SecretStr

from radar.common.clickhouse import (
    MIGRATIONS_TABLE,
    ClickHouseClient,
    ClickHouseError,
    Migration,
    MigrationFileError,
    apply_pending,
    load_migrations,
    split_statements,
)
from radar.common.settings import ClickHouseSettings

REPO_MIGRATIONS = Path(__file__).resolve().parents[3] / "infra/clickhouse/migrations"
SETTINGS = ClickHouseSettings(url="http://ch:8123", db="radar", user="u", password=SecretStr("p"))


class FakeClickHouse:
    """記錄執行過的 SQL；schema_migrations 的查詢回傳 applied，fail_on 出現時拋錯。"""

    def __init__(self, applied: set[int] | None = None, fail_on: str | None = None) -> None:
        self.applied = applied or set()
        self.fail_on = fail_on
        self.executed: list[str] = []

    def execute(self, sql: str) -> str:
        if self.fail_on and self.fail_on in sql:
            raise ClickHouseError("boom")
        self.executed.append(sql)
        if sql.startswith(f"SELECT version FROM {MIGRATIONS_TABLE}"):
            return "".join(f"{v}\n" for v in sorted(self.applied))
        return ""


def migration(version: int, *statements: str) -> Migration:
    return Migration(version=version, name=f"m{version}", statements=list(statements))


def test_split_statements_splits_on_semicolons():
    assert split_statements("CREATE TABLE a (x Int8);\nCREATE TABLE b (y Int8);") == [
        "CREATE TABLE a (x Int8)",
        "CREATE TABLE b (y Int8)",
    ]


def test_split_statements_ignores_comments_and_blank_statements():
    sql = "-- header; with semicolon\nSELECT 1; -- trailing\n;\n  \nSELECT 2 -- no semicolon"

    assert split_statements(sql) == ["SELECT 1", "SELECT 2"]


def test_split_statements_keeps_semicolon_inside_string_literal():
    sql = r"SELECT 'a;b', 'it\'s;', `c;d`; SELECT '--not comment'"

    assert split_statements(sql) == [r"SELECT 'a;b', 'it\'s;', `c;d`", "SELECT '--not comment'"]


def test_split_statements_empty_returns_empty():
    assert split_statements("-- only comments\n") == []


def test_load_migrations_sorted_by_version(tmp_path):
    (tmp_path / "0002_second.sql").write_text("SELECT 2;")
    (tmp_path / "0001_first.sql").write_text("SELECT 1;")

    loaded = load_migrations(tmp_path)

    assert [(m.version, m.name, m.statements) for m in loaded] == [
        (1, "first", ["SELECT 1"]),
        (2, "second", ["SELECT 2"]),
    ]


def test_load_migrations_bad_filename_raises(tmp_path):
    (tmp_path / "1_first.sql").write_text("SELECT 1;")

    with pytest.raises(MigrationFileError, match="NNNN"):
        load_migrations(tmp_path)


def test_load_migrations_duplicate_version_raises(tmp_path):
    (tmp_path / "0001_a.sql").write_text("SELECT 1;")
    (tmp_path / "0001_b.sql").write_text("SELECT 1;")

    with pytest.raises(MigrationFileError, match="duplicate"):
        load_migrations(tmp_path)


def test_load_migrations_repo_files_parse():
    loaded = load_migrations(REPO_MIGRATIONS)

    assert [m.version for m in loaded] == list(range(1, len(loaded) + 1))
    assert all(m.statements for m in loaded)


def test_execute_sends_credentials_database_and_body():
    seen = {}

    def handler(request):
        seen["headers"] = request.headers
        seen["params"] = dict(request.url.params)
        seen["body"] = request.content.decode()
        return httpx2.Response(200, text="1\n")

    client = ClickHouseClient(SETTINGS, transport=httpx2.MockTransport(handler))

    assert client.execute("SELECT 1") == "1\n"
    assert seen["headers"]["X-ClickHouse-User"] == "u"
    assert seen["headers"]["X-ClickHouse-Key"] == "p"
    assert seen["params"] == {"database": "radar"}
    assert seen["body"] == "SELECT 1"


def test_execute_non_200_raises_with_server_message():
    transport = httpx2.MockTransport(lambda r: httpx2.Response(500, text="Code: 60. UNKNOWN_TABLE"))
    client = ClickHouseClient(SETTINGS, transport=transport)

    with pytest.raises(ClickHouseError, match="UNKNOWN_TABLE"):
        client.execute("SELECT * FROM nope")


def test_apply_pending_runs_statements_and_records_versions():
    ch = FakeClickHouse()

    applied = apply_pending(ch, [migration(1, "CREATE A", "CREATE B")])

    assert [m.version for m in applied] == [1]
    assert ch.executed[-3:] == [
        "CREATE A",
        "CREATE B",
        f"INSERT INTO {MIGRATIONS_TABLE} (version, name) VALUES (1, 'm1')",
    ]


def test_apply_pending_skips_applied_versions():
    ch = FakeClickHouse(applied={1})

    applied = apply_pending(ch, [migration(1, "CREATE A"), migration(2, "CREATE B")])

    assert [m.version for m in applied] == [2]
    assert "CREATE A" not in ch.executed


def test_apply_pending_failure_does_not_record_version():
    ch = FakeClickHouse(fail_on="CREATE B")

    with pytest.raises(ClickHouseError):
        apply_pending(ch, [migration(1, "CREATE A"), migration(2, "CREATE B")])

    inserts = [s for s in ch.executed if s.startswith("INSERT")]
    assert inserts == [f"INSERT INTO {MIGRATIONS_TABLE} (version, name) VALUES (1, 'm1')"]

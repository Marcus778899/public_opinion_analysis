"""ClickHouse 的 HTTP client 與 schema migration（開發規格 7.9）。

migration 檔名為 NNNN_<name>.sql，已執行的版本記在 schema_migrations 表。
"""

import re
from dataclasses import dataclass
from pathlib import Path

import httpx2

from radar.common.settings import ClickHouseSettings

MIGRATIONS_TABLE = "schema_migrations"
_FILENAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class ClickHouseError(RuntimeError):
    """ClickHouse 回應非 200；訊息帶伺服器回傳的錯誤內容。"""


class MigrationFileError(ValueError):
    """migration 資料夾不存在、沒有檔案、檔名不符規則或版本重複。"""


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: list[str]


class ClickHouseClient:
    def __init__(self, settings: ClickHouseSettings, transport: httpx2.BaseTransport | None = None):
        self._client = httpx2.Client(
            base_url=settings.url,
            headers={
                "X-ClickHouse-User": settings.user,
                "X-ClickHouse-Key": settings.password.get_secret_value(),
            },
            params={"database": settings.db},
            transport=transport,
            timeout=30.0,
        )

    def execute(self, sql: str) -> str:
        resp = self._client.post("/", content=sql.encode())
        if resp.status_code != 200:
            raise ClickHouseError(f"{resp.status_code}: {resp.text.strip()}")
        return resp.text

    def close(self) -> None:
        self._client.close()


def split_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if quote:
            current.append(ch)
            if ch == "\\" and i + 1 < len(sql):
                current.append(sql[i + 1])
                i += 1
            elif ch == quote:
                quote = None
        elif ch in "'\"`":
            quote = ch
            current.append(ch)
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            i = len(sql) if end == -1 else end
            continue
        elif ch == ";":
            statements.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    statements.append("".join(current))
    return [s.strip() for s in statements if s.strip()]


def load_migrations(directory: Path) -> list[Migration]:
    # NOTE: 資料夾不存在時 glob 回傳空清單，會被當成「沒有待執行的 migration」而默默略過
    if not directory.is_dir():
        raise MigrationFileError(f"{directory}: migrations directory not found")
    paths = sorted(directory.glob("*.sql"))
    if not paths:
        raise MigrationFileError(f"{directory}: no migration files")
    migrations: dict[int, Migration] = {}
    for path in paths:
        match = _FILENAME.match(path.name)
        if match is None:
            raise MigrationFileError(f"{path.name}: expected NNNN_<name>.sql")
        version = int(match.group(1))
        if version in migrations:
            raise MigrationFileError(f"{path.name}: duplicate version {version}")
        migrations[version] = Migration(
            version=version, name=match.group(2), statements=split_statements(path.read_text())
        )
    return [migrations[v] for v in sorted(migrations)]


def applied_versions(client: ClickHouseClient) -> set[int]:
    client.execute(
        f"CREATE TABLE IF NOT EXISTS {MIGRATIONS_TABLE} "
        "(version UInt32, name String, applied_at DateTime DEFAULT now()) "
        "ENGINE = MergeTree ORDER BY version"
    )
    rows = client.execute(f"SELECT version FROM {MIGRATIONS_TABLE} FORMAT TabSeparated")
    return {int(v) for v in rows.split()}


def apply_pending(client: ClickHouseClient, migrations: list[Migration]) -> list[Migration]:
    """依序執行尚未執行的 migration，每個成功後才記錄版本；回傳本次執行的清單。"""
    # NOTE: ClickHouse 的 DDL 沒有 transaction，失敗時前面的語句已生效；
    # DDL 一律寫 IF NOT EXISTS，修正後重跑才不會卡在已建立的表
    done = applied_versions(client)
    applied: list[Migration] = []
    for m in migrations:
        if m.version in done:
            continue
        for statement in m.statements:
            client.execute(statement)
        # name 已由檔名規則限制為 [a-z0-9_]，可直接放進字串常值
        client.execute(
            f"INSERT INTO {MIGRATIONS_TABLE} (version, name) VALUES ({m.version}, '{m.name}')"
        )
        applied.append(m)
    return applied

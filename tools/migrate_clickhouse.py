"""套用 infra/clickhouse/migrations/ 中尚未執行的 migration。用法：make ch-migrate"""

from pathlib import Path

from radar.common.clickhouse import ClickHouseClient, apply_pending, load_migrations
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "infra/clickhouse/migrations"


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("ch-migrate")
    migrations = load_migrations(MIGRATIONS_DIR)
    client = ClickHouseClient(ClickHouseSettings())
    try:
        applied = apply_pending(client, migrations)
    finally:
        client.close()
    for m in applied:
        log.info("applied %04d_%s (%d statements)", m.version, m.name, len(m.statements))
    log.info("clickhouse schema up to date (%d applied)", len(applied))


if __name__ == "__main__":
    main()

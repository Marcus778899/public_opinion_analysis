"""擋住還是範例值的密碼（#119）：只讀環境變數，只印變數名稱，不印值。

`init` 最先跑；失敗時非 0 結束，後面的建表、建 topic、migration 不會執行。
"""

import os
import sys
from collections.abc import Mapping

from radar.common.log import log, setup_logging

SECRET_NAMES = (
    "POSTGRES_PASSWORD",
    "CLICKHOUSE_PASSWORD",
    "CLICKHOUSE_GRAFANA_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
)
PLACEHOLDERS = frozenset({"change-me", "changeme", "change_me"})


def is_placeholder(value: str | None) -> bool:
    if value is None or not value.strip():
        return True
    return value.strip().lower() in PLACEHOLDERS


def find_bad(env: Mapping[str, str]) -> list[str]:
    return [name for name in SECRET_NAMES if is_placeholder(env.get(name))]


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("check-secrets")
    bad = find_bad(os.environ)
    if bad:
        log.error("these variables are empty or still the example value: %s", ", ".join(bad))
        sys.exit(1)
    log.info("all %d secrets are set", len(SECRET_NAMES))


if __name__ == "__main__":
    main()

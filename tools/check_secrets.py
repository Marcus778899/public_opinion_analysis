"""擋住還是範例值的密碼（#119）：只讀環境變數，只印變數名稱，不印值。

`init` 與 compose 的 `secret-check` 都先跑；失敗時非 0 結束，後面的服務不會啟動。
"""

import os
import sys
from collections.abc import Mapping

try:
    from radar.common.log import log, setup_logging
except ImportError:  # NOTE: secret-check 跑在純 python image，沒有 radar 套件與 loggerhelper
    from types import SimpleNamespace

    def _emit(level: str):
        def write(msg: str, *args: object) -> None:
            sys.stderr.write(f"{level} check-secrets {msg % args}\n")

        return write

    log = SimpleNamespace(
        info=_emit("INFO"),
        error=_emit("ERROR"),
        catch=lambda **_: lambda fn: fn,
    )

    def setup_logging(service: str) -> None:
        return None


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

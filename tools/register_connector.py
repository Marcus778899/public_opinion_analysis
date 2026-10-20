"""註冊或更新 Debezium connector（冪等）。用法：make connector"""

import os
from pathlib import Path

import httpx2

from radar.common.kafka.connect import (
    load_connector_spec,
    put_connector,
    wait_until_ready,
    wait_until_running,
)
from radar.common.log import log, setup_logging
from radar.common.settings import ConnectSettings

CONNECTOR_FILE = Path(__file__).resolve().parents[1] / "infra/debezium/radar-cdc.json"
RUNNING_TIMEOUT_S = 60.0


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("register-connector")
    settings = ConnectSettings()
    spec = load_connector_spec(CONNECTOR_FILE, os.environ)
    with httpx2.Client(base_url=settings.url, timeout=10.0) as client:
        wait_until_ready(client, settings.ready_timeout_s)
        created = put_connector(client, spec)
        log.info("connector %s %s", spec.name, "created" if created else "updated")
        wait_until_running(client, spec.name, RUNNING_TIMEOUT_S)
    log.info("connector %s running", spec.name)


if __name__ == "__main__":
    main()

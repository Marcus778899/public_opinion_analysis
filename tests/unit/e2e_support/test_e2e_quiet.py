import os
from pathlib import Path

import yaml

from tests.e2e import conftest as e2e_conftest

INFRA = Path(__file__).resolve().parents[3] / "infra"
QUIET_KEYS = ("SLACK_WEBHOOK_URL", "SLACK_BOT_TOKEN", "CDC_WATCHDOG_HEARTBEAT_URL")


def load_services(name: str) -> dict[str, dict]:
    return yaml.safe_load((INFRA / name).read_text())["services"]


def test_e2e_compose_override_blanks_notifications_for_every_app_service():
    base = load_services("docker-compose.yaml")
    override = load_services("docker-compose.e2e.yaml")
    # 讀得到 .env 的 app 服務（label-stream 屬於 labeling profile，e2e 不啟動）
    app_services = [
        name for name, svc in base.items() if "env_file" in svc and "app" in svc.get("profiles", [])
    ]

    assert "cdc-watchdog" in app_services
    for name in app_services:
        env = override.get(name, {}).get("environment", {})
        assert {k: env.get(k) for k in QUIET_KEYS} == dict.fromkeys(QUIET_KEYS, ""), name


def test_e2e_pytest_configure_clears_notification_env(monkeypatch):
    for key in QUIET_KEYS:
        monkeypatch.setenv(key, "https://example.invalid/should-not-be-used")

    e2e_conftest.pytest_configure(None)

    assert {k: os.environ[k] for k in QUIET_KEYS} == dict.fromkeys(QUIET_KEYS, "")

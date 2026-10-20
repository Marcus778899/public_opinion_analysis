from pathlib import Path

import yaml

COMPOSE = Path(__file__).resolve().parents[3] / "infra" / "docker-compose.yaml"
APP_IMAGE = "radar-app:latest"


def app_services() -> dict[str, dict]:
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    return {name: svc for name, svc in services.items() if svc.get("image") == APP_IMAGE}


def test_every_app_service_gets_container_network_addresses():
    # 2026-10-17：bot 服務漏了 app-env，啟動後連到 localhost 的 Kafka（開發規格 7.21）
    services = app_services()

    assert "bot" in services
    for name, svc in services.items():
        env = svc.get("environment") or {}
        assert env.get("KAFKA_BOOTSTRAP_SERVERS", "").startswith("kafka_1:"), name
        assert env.get("POSTGRES_HOST") == "postgres", name
        assert env.get("CLICKHOUSE_URL") == "http://clickhouse:8123", name

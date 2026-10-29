"""infra-secret-guard 驗收測試：靜態檢查 infra/docker-compose.yaml（#254、D-035）。"""

from pathlib import Path

import pytest
import yaml

COMPOSE = Path(__file__).resolve().parents[4] / "infra" / "docker-compose.yaml"
GUARDED = ["postgres", "clickhouse", "grafana"]
KAFKA = ["kafka_1", "kafka_2", "kafka_3"]
APP = [
    "api",
    "scheduler",
    "crawler",
    "ingest",
    "cdc-watchdog",
    "inference",
    "inference-shadow",
    "heat",
    "bot",
    "label-stream",
]


@pytest.fixture(scope="module")
def services() -> dict[str, dict]:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def _command_text(svc: dict) -> str:
    cmd = svc.get("command", "")
    return cmd if isinstance(cmd, str) else " ".join(str(c) for c in cmd)


@pytest.fixture(scope="module")
def guard_name(services: dict[str, dict]) -> str:
    found = [
        name
        for name, svc in services.items()
        if "check_secrets.py" in _command_text(svc) and not svc.get("profiles")
    ]
    assert len(found) == 1, f"預設 profile 應恰有一個跑 check_secrets.py 的服務，實際：{found}"
    return found[0]


def test_default_profile_has_one_shot_secret_check_service(
    services: dict[str, dict], guard_name: str
) -> None:
    svc = services[guard_name]
    assert not svc.get("profiles")
    assert svc.get("restart") == "no"


@pytest.mark.parametrize("name", GUARDED)
def test_infra_service_waits_for_secret_check_completion(
    services: dict[str, dict], guard_name: str, name: str
) -> None:
    deps = services[name]["depends_on"]
    assert isinstance(deps, dict)
    assert deps[guard_name]["condition"] == "service_completed_successfully"


def test_secret_check_service_does_not_depend_on_guarded_services(
    services: dict[str, dict], guard_name: str
) -> None:
    deps = services[guard_name].get("depends_on") or {}
    assert not set(deps) & set(GUARDED)


def test_postgres_port_binds_loopback_only(services: dict[str, dict]) -> None:
    ports = services["postgres"]["ports"]
    assert ports
    assert all(str(p).startswith("127.0.0.1:") for p in ports)
    assert all(str(p).endswith(":5432") for p in ports)


# ---- 守門測試（現況已通過，改動後不可壞）----


def test_guard_init_still_runs_secret_check_first(services: dict[str, dict]) -> None:
    init = services["init"]
    text = _command_text(init)
    assert "check_secrets.py" in text
    assert text.index("check_secrets.py") < text.index("alembic upgrade head")
    assert init["profiles"] == ["app"]


def test_guard_clickhouse_and_grafana_ports_stay_loopback(services: dict[str, dict]) -> None:
    assert services["clickhouse"]["ports"] == ["127.0.0.1:8123:8123"]
    assert services["grafana"]["ports"] == ["127.0.0.1:${GRAFANA_PORT:?GRAFANA_PORT 未設定}:3000"]


def test_guard_grafana_still_waits_for_healthy_clickhouse(services: dict[str, dict]) -> None:
    assert services["grafana"]["depends_on"]["clickhouse"] == {"condition": "service_healthy"}


@pytest.mark.parametrize(
    ("name", "port"), [("kafka_1", "9092:9092"), ("kafka_2", "9094:9094"), ("kafka_3", "9096:9096")]
)
def test_guard_kafka_ports_unchanged(services: dict[str, dict], name: str, port: str) -> None:
    assert services[name]["ports"] == [port]


@pytest.mark.parametrize("name", KAFKA)
def test_guard_kafka_has_no_depends_on(services: dict[str, dict], name: str) -> None:
    assert "depends_on" not in services[name]


@pytest.mark.parametrize("name", [n for n in APP if n != "api"])
def test_guard_app_service_depends_only_on_init(services: dict[str, dict], name: str) -> None:
    assert services[name]["depends_on"] == {"init": {"condition": "service_completed_successfully"}}
    assert "ports" not in services[name]


def test_guard_api_depends_only_on_init_and_port_unchanged(services: dict[str, dict]) -> None:
    assert services["api"]["depends_on"] == {
        "init": {"condition": "service_completed_successfully"}
    }
    assert services["api"]["ports"] == ["127.0.0.1:8000:8000"]


def test_guard_init_depends_on_unchanged(services: dict[str, dict]) -> None:
    assert services["init"]["depends_on"] == {
        "postgres": {"condition": "service_healthy"},
        "connect": {"condition": "service_healthy"},
        "clickhouse": {"condition": "service_healthy"},
        "kafka_1": {"condition": "service_healthy"},
        "kafka_2": {"condition": "service_healthy"},
        "kafka_3": {"condition": "service_healthy"},
    }

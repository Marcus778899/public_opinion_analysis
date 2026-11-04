"""驗收 connect-resilience（開發規格 7.30 B）：compose 靜態檢查。

注意：三個 CONNECT_*_STORAGE_MIN_INSYNC_REPLICAS 若經調查 Connect 不套用而被拿掉（派工單說明），
min.isr 測試接受「三個都不存在」；只存在一部分或值不是 1 則失敗。
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
CFG = yaml.safe_load((ROOT / "infra/docker-compose.yaml").read_text(encoding="utf-8"))
CONNECT = CFG["services"]["connect"]
INIT = CFG["services"]["init"]

KINDS = ["CONFIG", "OFFSET", "STATUS"]


def env_of(service: dict) -> dict[str, str]:
    env = service["environment"]
    if isinstance(env, list):
        return dict(item.split("=", 1) for item in env)
    return {k: str(v) for k, v in env.items()}


@pytest.mark.parametrize("kind", KINDS)
def test_internal_topic_replication_factor_is_2(kind: str) -> None:
    assert env_of(CONNECT)[f"CONNECT_{kind}_STORAGE_REPLICATION_FACTOR"] == "2"


def test_internal_topic_min_insync_replicas_is_1_when_set() -> None:
    env = env_of(CONNECT)
    keys = [f"CONNECT_{k}_STORAGE_MIN_INSYNC_REPLICAS" for k in KINDS]
    present = [k for k in keys if k in env]
    assert len(present) in (0, 3), f"min.isr must be set on all three topics or none: {present}"
    assert all(env[k] == "1" for k in present)


def test_internal_topic_names_unchanged() -> None:
    env = env_of(CONNECT)
    assert env["CONFIG_STORAGE_TOPIC"] == "connect_configs"
    assert env["OFFSET_STORAGE_TOPIC"] == "connect_offsets"
    assert env["STATUS_STORAGE_TOPIC"] == "connect_statuses"


def healthcheck_cmd() -> str:
    test = CONNECT["healthcheck"]["test"]
    return test if isinstance(test, str) else " ".join(test)


def test_connect_healthcheck_checks_health_endpoint() -> None:
    assert ":8083/health" in healthcheck_cmd()


def test_connect_healthcheck_checks_connector_exists() -> None:
    assert "/connectors/radar-cdc" in healthcheck_cmd()


def test_connect_healthcheck_requires_both_checks() -> None:
    cmd = healthcheck_cmd()
    assert "&&" in cmd
    assert cmd.index("/health") < cmd.index("/connectors/radar-cdc")
    assert "||" not in cmd


def test_connect_healthcheck_has_start_period_for_fresh_environment() -> None:
    assert "start_period" in CONNECT["healthcheck"]
    value = str(CONNECT["healthcheck"]["start_period"])
    assert value in ("300s", "5m", "5m0s")


def test_init_depends_on_connect_service_started() -> None:
    assert INIT["depends_on"]["connect"] == {"condition": "service_started"}


def test_init_other_dependencies_stay_healthy() -> None:
    deps = INIT["depends_on"]
    for name in ("postgres", "clickhouse", "kafka_1", "kafka_2", "kafka_3"):
        assert deps[name] == {"condition": "service_healthy"}

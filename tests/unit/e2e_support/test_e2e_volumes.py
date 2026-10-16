from pathlib import Path

import yaml

INFRA = Path(__file__).resolve().parents[3] / "infra"


def load(name: str) -> dict:
    return yaml.safe_load((INFRA / name).read_text())


def mounts(service: dict) -> list[str]:
    return [v for v in service.get("volumes", []) if isinstance(v, str)]


def test_e2e_override_moves_every_app_log_mount_to_e2e_volume():
    # #29：e2e-down 的 down -v 會刪掉 e2e 服務掛的 volume，與開發環境共用就會刪掉開發的 log
    base = load("docker-compose.yaml")
    e2e = load("docker-compose.e2e.yaml")
    shared = [
        name
        for name, svc in base["services"].items()
        if any(m.startswith("app_logs:") for m in mounts(svc))
    ]

    assert "crawler" in shared
    for name in shared:
        assert "e2e_app_logs:/app/log" in mounts(e2e["services"].get(name, {})), name


def test_e2e_declares_its_own_log_volume():
    assert "e2e_app_logs" in load("docker-compose.e2e.yaml")["volumes"]


def test_e2e_override_never_mounts_shared_dev_volumes():
    dev_volumes = set(load("docker-compose.yaml")["volumes"])
    e2e = load("docker-compose.e2e.yaml")

    for name, svc in e2e["services"].items():
        for m in mounts(svc):
            assert m.split(":", 1)[0] not in dev_volumes, (name, m)

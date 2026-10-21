from pathlib import Path

import yaml

INFRA = Path(__file__).resolve().parents[3] / "infra"
GRAFANA_DATA_DIR = "/var/lib/grafana"


def load(name: str) -> dict:
    return yaml.safe_load((INFRA / name).read_text())


def merged_mounts(service: str) -> dict[str, str]:
    # compose 合併 volumes 清單時以容器內路徑（target）為鍵，後者覆蓋前者
    result: dict[str, str] = {}
    for name in ("docker-compose.yaml", "docker-compose.e2e.yaml"):
        svc = load(name)["services"].get(service, {})
        for m in svc.get("volumes", []):
            if isinstance(m, str):
                source, target = m.split(":")[:2]
                result[target] = source
    return result


def test_dev_grafana_mounts_grafana_data():
    base = load("docker-compose.yaml")["services"]["grafana"]

    assert f"grafana_data:{GRAFANA_DATA_DIR}" in base["volumes"]


def test_e2e_merged_grafana_does_not_mount_dev_grafana_data():
    # UAT F-1：e2e 的 down -v 會連開發環境的 grafana_data 一起刪掉
    sources = merged_mounts("grafana")

    assert sources[GRAFANA_DATA_DIR] != "grafana_data"
    assert "grafana_data" not in sources.values()


def test_e2e_merged_grafana_data_uses_e2e_prefixed_volume():
    source = merged_mounts("grafana")[GRAFANA_DATA_DIR]

    assert source == "e2e_grafana_data"


def test_e2e_declares_its_own_grafana_volume():
    assert "e2e_grafana_data" in load("docker-compose.e2e.yaml")["volumes"]

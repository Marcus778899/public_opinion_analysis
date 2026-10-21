from pathlib import Path

import pytest
import yaml

INFRA = Path(__file__).resolve().parents[3] / "infra"


def load(name: str) -> dict:
    return yaml.safe_load((INFRA / name).read_text())


def mount_pair(m: str | dict) -> tuple[str, str]:
    if isinstance(m, str):
        source, target = m.split(":")[:2]
        return target, source
    return m["target"], m.get("source", "")


def merged_sources(base: dict, e2e: dict) -> dict[str, dict[str, str]]:
    # compose 合併 volumes 清單時以容器內路徑（target）為鍵，後者覆蓋前者
    result: dict[str, dict[str, str]] = {}
    for doc in (base, e2e):
        for name, svc in doc["services"].items():
            mounts = result.setdefault(name, {})
            for m in svc.get("volumes", []):
                target, source = mount_pair(m)
                mounts[target] = source
    return result


def offenders(base: dict, e2e: dict) -> list[str]:
    dev_volumes = set(base.get("volumes") or {})
    merged = merged_sources(base, e2e)
    return [
        f"{name}:{target}={source}"
        for name in base["services"]
        for target, source in merged[name].items()
        if source in dev_volumes
    ]


def test_e2e_merged_services_mount_no_dev_volume():
    assert offenders(load("docker-compose.yaml"), load("docker-compose.e2e.yaml")) == []


def test_dev_compose_declares_volumes_to_check():
    assert load("docker-compose.yaml")["volumes"]


def test_fake_compose_with_unoverridden_dev_volume_is_caught():
    base = {
        "services": {"a": {"volumes": ["dev_data:/data"]}, "b": {"volumes": ["dev_data:/x"]}},
        "volumes": {"dev_data": None},
    }
    e2e = {"services": {"a": {"volumes": ["e2e_data:/data"]}}}

    assert offenders(base, e2e) == ["b:/x=dev_data"]


def test_fake_compose_with_long_syntax_dev_volume_is_caught():
    base = {
        "services": {"a": {"volumes": [{"type": "volume", "source": "dev_data", "target": "/d"}]}},
        "volumes": {"dev_data": None},
    }

    assert offenders(base, {"services": {}}) == ["a:/d=dev_data"]


@pytest.mark.parametrize("e2e_source", ["e2e_data", "./local"])
def test_fake_compose_overridden_with_other_source_passes(e2e_source):
    base = {"services": {"a": {"volumes": ["dev_data:/data"]}}, "volumes": {"dev_data": None}}
    e2e = {"services": {"a": {"volumes": [f"{e2e_source}:/data"]}}}

    assert offenders(base, e2e) == []

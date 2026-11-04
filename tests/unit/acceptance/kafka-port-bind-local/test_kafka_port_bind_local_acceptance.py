"""驗收 kafka-port-bind-local：對外 port 全綁 127.0.0.1，開發規格同步。"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
COMPOSE = (ROOT / "infra/docker-compose.yaml").read_text(encoding="utf-8")
SPEC = (ROOT / "docs/development-spec.md").read_text(encoding="utf-8")


def _port_entries() -> list[str]:
    entries: list[str] = []
    lines = COMPOSE.splitlines()
    for i, line in enumerate(lines):
        if re.match(r"^\s+ports:\s*$", line):
            indent = len(line) - len(line.lstrip())
            for nxt in lines[i + 1 :]:
                m = re.match(r"^(\s+)-\s*(.+?)\s*(#.*)?$", nxt)
                if not m or len(m.group(1)) <= indent:
                    break
                entries.append(m.group(2).strip("\"'"))
    return entries


def test_kafka_ports_bind_loopback_only():
    entries = _port_entries()
    for port in (9092, 9094, 9096):
        assert f"127.0.0.1:{port}:{port}" in entries
        assert f"{port}:{port}" not in entries


def test_no_published_port_without_loopback_ip():
    entries = _port_entries()
    assert entries
    bad = [e for e in entries if not e.startswith("127.0.0.1:")]
    assert bad == []


def test_no_published_port_binds_all_interfaces():
    assert "0.0.0.0:" not in COMPOSE


def test_spec_states_kafka_loopback_and_host_tools_address():
    assert "localhost:9092,9094,9096" in SPEC
    assert re.search(r"Kafka[^\n]{0,60}(只綁|綁)[^\n]{0,20}(本機|127\.0\.0\.1)", SPEC)


def test_spec_720_step6_expects_at_least_one_alert():
    step6 = next(line for line in SPEC.splitlines() if re.match(r"^\s*6\. 看結果", line))
    assert "至少 1 則警示" in step6
    assert "預期收到 1 則文章警示" not in step6

"""驗收 inference-resource-limit：inference 有 CPU／記憶體上限，shadow 不變（7.30 C，#289）。"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
COMPOSE = (ROOT / "infra/docker-compose.yaml").read_text(encoding="utf-8")


def _service_block(name: str) -> str:
    lines = COMPOSE.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln == f"  {name}:")
    body: list[str] = []
    for ln in lines[start + 1 :]:
        if re.match(r"^ {0,2}\S", ln):
            break
        body.append(ln)
    return "\n".join(body)


def _field(block: str, key: str) -> str | None:
    m = re.search(rf"^    {key}:\s*['\"]?([^'\"#\s]+)['\"]?\s*(#.*)?$", block, re.MULTILINE)
    return m.group(1) if m else None


def _env(block: str, key: str) -> str | None:
    m = re.search(rf"^      {key}:\s*['\"]?([^'\"#\s]*)['\"]?\s*(#.*)?$", block, re.MULTILINE)
    return m.group(1) if m else None


def test_inference_cpus_is_2() -> None:
    assert _field(_service_block("inference"), "cpus") == "2"


def test_inference_mem_limit_is_2g() -> None:
    assert _field(_service_block("inference"), "mem_limit") == "2g"


def test_inference_threads_is_2() -> None:
    assert _env(_service_block("inference"), "INFERENCE_THREADS") == "2"


def test_inference_threads_is_quoted_string() -> None:
    assert re.search(
        r"^      INFERENCE_THREADS:\s*(['\"])2\1", _service_block("inference"), re.MULTILINE
    )


def test_inference_role_stays_primary() -> None:
    assert _env(_service_block("inference"), "INFERENCE_ROLE") == "primary"


def test_shadow_limits_unchanged() -> None:
    block = _service_block("inference-shadow")
    assert _field(block, "cpus") == "2"
    assert _field(block, "mem_limit") == "1.5g"
    assert _env(block, "INFERENCE_THREADS") == "2"
    assert _env(block, "INFERENCE_ROLE") == "shadow"

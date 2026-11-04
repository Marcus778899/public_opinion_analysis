"""ci-token-order：integration job 的工具 checkout 順序與 Makefile 註解（#276、#277）。"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
RISKY = ("docker compose", "uv ", "make ", "pip ", "pytest")
GATE_COND = (
    "steps.changes.outputs.code == 'true' && github.event_name == 'pull_request'"
    " && github.base_ref == 'develop'"
)


@pytest.fixture(scope="module")
def steps() -> list[dict]:
    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
    return ci["jobs"]["integration"]["steps"]


def _text(step: dict) -> str:
    return f"{step.get('run', '')} {step.get('uses', '')}"


def _idx(steps: list[dict], name: str) -> int:
    return next(i for i, s in enumerate(steps) if s.get("name") == name)


def _tool_checkout(steps: list[dict]) -> dict:
    return steps[_idx(steps, "Checkout agent-engineering")]


def test_tool_steps_come_after_git_diff_step(steps: list[dict]) -> None:
    diff = next(i for i, s in enumerate(steps) if "git diff --name-only" in _text(s))
    assert _idx(steps, "Locate agent-engineering") > diff
    assert _idx(steps, "Checkout agent-engineering") > diff


def test_tool_steps_come_before_any_docker_uv_or_make_step(steps: list[dict]) -> None:
    last_tool = max(
        _idx(steps, "Locate agent-engineering"), _idx(steps, "Checkout agent-engineering")
    )
    for i, s in enumerate(steps):
        if "uses" in s and "setup-uv" in s["uses"]:
            assert i > last_tool, s.get("name")
        if any(k in s.get("run", "") for k in RISKY):
            assert i > last_tool, s.get("name")


def test_locate_comes_before_checkout(steps: list[dict]) -> None:
    assert _idx(steps, "Locate agent-engineering") < _idx(steps, "Checkout agent-engineering")


def test_tool_steps_keep_if_condition(steps: list[dict]) -> None:
    for name in ("Locate agent-engineering", "Checkout agent-engineering"):
        assert steps[_idx(steps, name)]["if"] == GATE_COND, name


def test_tool_checkout_does_not_persist_credentials(steps: list[dict]) -> None:
    assert _tool_checkout(steps)["with"]["persist-credentials"] is False


def test_tool_checkout_still_uses_ae_token_and_path(steps: list[dict]) -> None:
    w = _tool_checkout(steps)["with"]
    assert "AE_TOKEN" in w["token"]
    assert w["path"] == ".claude/skills/agent-engineering"


def test_coverage_gate_steps_stay_after_tests(steps: list[dict]) -> None:
    tests = _idx(steps, "Unit and integration tests with coverage")
    assert _idx(steps, "Set up Python for coverage gate") > tests
    assert _idx(steps, "Coverage of changed lines") > tests


def test_makefile_does_not_mention_check_env_py() -> None:
    assert "check_env.py" not in (ROOT / "Makefile").read_text()


def test_makefile_setup_comment_mentions_check_env_setup_command() -> None:
    line = next(
        ln for ln in (ROOT / "Makefile").read_text().splitlines() if ln.startswith("setup:")
    )
    assert "check-env setup" in line

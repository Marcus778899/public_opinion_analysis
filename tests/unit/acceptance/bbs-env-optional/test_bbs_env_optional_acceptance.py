"""bbs-env-optional 驗收測試（D-050、D-009：PTT_BBS_* 改回選填）。"""

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[4]
VARS = ("PTT_BBS_USERNAME", "PTT_BBS_PASSWORD")


def _lines() -> list[str]:
    return (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()


def _load_tool() -> ModuleType:
    sys.modules.pop("PyPtt", None)
    spec = importlib.util.spec_from_file_location("bbs_spike_env_opt", ROOT / "tools/bbs_spike.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("name", VARS)
def test_env_example_var_is_commented_out_without_value(name: str) -> None:
    lines = _lines()
    assert f"# {name}=" in lines
    assert not any(ln.startswith(f"{name}=") for ln in lines)


def test_env_example_has_no_uncommented_ptt_bbs_line() -> None:
    assert not [ln for ln in _lines() if re.match(r"\s*PTT_BBS_", ln)]


def test_env_example_commented_vars_have_no_value_after_equals() -> None:
    for ln in _lines():
        m = re.match(r"\s*#\s*PTT_BBS_(?:USERNAME|PASSWORD)=(.*)$", ln)
        if m:
            assert m.group(1).strip() == ""


def test_env_example_section_cites_d050_not_d046() -> None:
    lines = _lines()
    idx = next(i for i, ln in enumerate(lines) if ln == "# PTT_BBS_USERNAME=")
    header = "\n".join(lines[max(0, idx - 4) : idx])
    assert "D-050" in header
    assert "D-046" not in header


@pytest.mark.parametrize("missing", [VARS, VARS[:1], VARS[1:]])
def test_tool_refuses_login_when_vars_unset_naming_only_variables(
    monkeypatch: pytest.MonkeyPatch, missing: tuple[str, ...]
) -> None:
    tool = _load_tool()
    monkeypatch.setenv("PTT_BBS_USERNAME", "x_user")
    monkeypatch.setenv("PTT_BBS_PASSWORD", "x_pass")
    for name in missing:
        monkeypatch.delenv(name)
    with pytest.raises(SystemExit) as exc:
        tool.load_credentials()
    msg = str(exc.value)
    for name in missing:
        assert name in msg
    assert "x_user" not in msg and "x_pass" not in msg


def test_tool_refuses_login_when_vars_are_empty_strings(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = _load_tool()
    for name in VARS:
        monkeypatch.setenv(name, "")
    with pytest.raises(SystemExit):
        tool.load_credentials()

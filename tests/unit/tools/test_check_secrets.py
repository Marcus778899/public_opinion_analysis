import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def _load() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "tools" / "check_secrets.py"
    spec = importlib.util.spec_from_file_location("check_secrets", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cs = _load()
GOOD = {name: f"real-{i}-Xy9" for i, name in enumerate(cs.SECRET_NAMES)}


@pytest.mark.parametrize(
    "value", [None, "", "   ", "change-me", "CHANGE_ME", "changeme", "Change_Me", " ChangeMe "]
)
def test_is_placeholder_empty_or_example_values_returns_true(value: str | None) -> None:
    assert cs.is_placeholder(value) is True


@pytest.mark.parametrize("value", ["my-change-me-pass-77", "s3cret", "change-me2"])
def test_is_placeholder_real_values_returns_false(value: str) -> None:
    assert cs.is_placeholder(value) is False


def test_find_bad_all_good_returns_empty() -> None:
    assert cs.find_bad(GOOD) == []


def test_find_bad_unset_empty_and_placeholder_are_listed_in_order() -> None:
    env = dict(GOOD)
    del env["POSTGRES_PASSWORD"]
    env["CLICKHOUSE_PASSWORD"] = ""
    env["GRAFANA_ADMIN_PASSWORD"] = "change-me"
    expected = ["POSTGRES_PASSWORD", "CLICKHOUSE_PASSWORD", "GRAFANA_ADMIN_PASSWORD"]
    assert cs.find_bad(env) == expected


def test_main_good_env_returns_normally(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in GOOD.items():
        monkeypatch.setenv(k, v)
    cs.main()


def test_main_bad_env_exits_nonzero_without_printing_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for k, v in GOOD.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("POSTGRES_PASSWORD", "change-me")
    with pytest.raises(SystemExit) as exc:
        cs.main()
    assert exc.value.code == 1
    out = capsys.readouterr()
    assert "change-me" not in out.out + out.err


def _load_without_radar(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.setitem(sys.modules, "radar.common.log", None)
    return _load()


def test_fallback_logging_without_radar_good_env_returns_normally(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load_without_radar(monkeypatch)
    for k, v in GOOD.items():
        monkeypatch.setenv(k, v)
    mod.main()
    assert "all 4 secrets are set" in capsys.readouterr().err


def test_fallback_logging_without_radar_bad_env_exits_with_names_only(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load_without_radar(monkeypatch)
    for k, v in GOOD.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "change-me")
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "GRAFANA_ADMIN_PASSWORD" in err
    assert "change-me" not in err

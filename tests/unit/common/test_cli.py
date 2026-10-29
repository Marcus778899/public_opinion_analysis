import pytest
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from radar.common.cli import fail, load_settings
from radar.common.csv_safe import csv_safe


def test_fail_exits_nonzero_and_prints_one_line(capsys):
    with pytest.raises(SystemExit) as exc:
        fail("boom")
    assert exc.value.code == 1
    assert capsys.readouterr().err == "error: boom\n"


class _Cfg(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XCLI_")

    user: str
    password: str
    url: str = "http://x"


def test_load_settings_names_only_missing_vars_and_hint(monkeypatch, capsys):
    monkeypatch.setenv("XCLI_USER", "u")
    monkeypatch.delenv("XCLI_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        load_settings(_Cfg)
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "XCLI_PASSWORD" in err
    assert "XCLI_USER" not in err
    assert "uv run --env-file .env" in err


def test_load_settings_returns_settings_when_complete(monkeypatch):
    monkeypatch.setenv("XCLI_USER", "u")
    monkeypatch.setenv("XCLI_PASSWORD", "p")
    assert load_settings(_Cfg).user == "u"


def test_load_settings_reraises_other_validation_errors(monkeypatch):
    monkeypatch.setenv("XCLI_URL", "x")

    class Typed(BaseSettings):
        model_config = SettingsConfigDict(env_prefix="XCLI_")
        url: int

    with pytest.raises(ValidationError):
        load_settings(Typed)


@pytest.mark.parametrize("value", ["=1", "+1", "-1", "@a", "\tx", "\rx"])
def test_csv_safe_prefixes_formula_starts(value):
    assert csv_safe(value) == "'" + value


@pytest.mark.parametrize("value", ["", "abc", "a=b", " =x"])
def test_csv_safe_leaves_other_values(value):
    assert csv_safe(value) == value

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
SCRIPT = ROOT / "tools" / "check_secrets.py"
COMPOSE = ROOT / "infra" / "docker-compose.yaml"
ENV_EXAMPLE = ROOT / ".env.example"
NAMES = [
    "POSTGRES_PASSWORD",
    "CLICKHOUSE_PASSWORD",
    "CLICKHOUSE_GRAFANA_PASSWORD",
    "GRAFANA_ADMIN_PASSWORD",
]
GOOD = {name: f"s3cret-{i}-Xy9" for i, name in enumerate(NAMES)}


def _run(values: dict[str, str], unset: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in NAMES}
    env["PYTHONPATH"] = str(ROOT / "src")
    env.update(values)
    for name in unset:
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, str(SCRIPT)], env=env, capture_output=True, text=True, cwd=ROOT
    )


def _out(r: subprocess.CompletedProcess[str]) -> str:
    return r.stdout + r.stderr


def test_all_four_real_values_pass_with_exit_zero() -> None:
    assert _run(GOOD).returncode == 0


@pytest.mark.parametrize(
    "placeholder", ["change-me", "CHANGE_ME", "changeme", "Change_Me", "ChangeMe"]
)
@pytest.mark.parametrize("name", NAMES)
def test_placeholder_value_fails_and_names_variable_without_value(
    name: str, placeholder: str
) -> None:
    r = _run({**GOOD, name: placeholder})
    assert r.returncode != 0
    assert name in _out(r)
    assert placeholder not in _out(r)


@pytest.mark.parametrize("name", NAMES)
def test_empty_value_fails_and_names_variable(name: str) -> None:
    r = _run({**GOOD, name: ""})
    assert r.returncode != 0
    assert name in _out(r)


@pytest.mark.parametrize("name", NAMES)
def test_unset_variable_fails_and_names_variable(name: str) -> None:
    r = _run(GOOD, unset=(name,))
    assert r.returncode != 0
    assert name in _out(r)


def test_multiple_bad_values_are_all_listed_and_good_values_never_printed() -> None:
    r = _run({**GOOD, NAMES[0]: "change-me", NAMES[2]: ""})
    assert r.returncode != 0
    assert NAMES[0] in _out(r)
    assert NAMES[2] in _out(r)
    for name in (NAMES[1], NAMES[3]):
        assert GOOD[name] not in _out(r)


def test_values_merely_containing_change_me_are_not_placeholders() -> None:
    r = _run({**GOOD, NAMES[0]: "my-change-me-pass-77"})
    assert r.returncode == 0


def test_passing_run_does_not_print_secret_values() -> None:
    r = _run(GOOD)
    for value in GOOD.values():
        assert value not in _out(r)


def _init_command() -> str:
    data = yaml.safe_load(COMPOSE.read_text())
    cmd = data["services"]["init"]["command"]
    return " ".join(cmd) if isinstance(cmd, list) else str(cmd)


def test_init_runs_secret_check_before_every_other_step() -> None:
    cmd = _init_command()
    assert "check_secrets.py" in cmd
    first = cmd.index("check_secrets.py")
    for step in ("alembic", "create_topics.py", "migrate_clickhouse.py", "register_connector.py"):
        assert step in cmd
        assert first < cmd.index(step), step


def test_init_chains_secret_check_with_and_so_failure_stops_later_steps() -> None:
    cmd = _init_command()
    after_check = cmd.split("check_secrets.py", 1)[1]
    assert re.match(r"\s*&&", after_check)
    assert ";" not in cmd and "||" not in cmd


def test_env_example_passwords_use_uppercase_placeholder() -> None:
    lines = {
        k: v for k, _, v in (line.partition("=") for line in ENV_EXAMPLE.read_text().splitlines())
    }
    for name in NAMES:
        assert lines[name].strip() == "CHANGE_ME", name


def test_check_env_lists_example_passwords_as_required() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_env

        parsed = check_env.parse(ENV_EXAMPLE)
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    for name in NAMES:
        assert parsed[name][0] == "CHANGE_ME", name

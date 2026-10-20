"""開發規格 7.26 做法 1、3～5、10～12 的靜態檢查（compose.yaml、compose.ci.yaml、ci.yml）。"""

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
SERVICES = {"kafka", "postgres", "clickhouse", "test"}
DEPS = ("kafka", "postgres", "clickhouse")


def _load(rel: str) -> dict:
    path = ROOT / rel
    assert path.is_file(), f"{rel} 不存在"
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict)
    return data


@pytest.fixture(scope="module")
def compose() -> dict:
    return _load("compose.yaml")


@pytest.fixture(scope="module")
def compose_ci() -> dict:
    return _load("compose.ci.yaml")


@pytest.fixture(scope="module")
def ci() -> dict:
    return _load(".github/workflows/ci.yml")


def _blob(data: object) -> str:
    return json.dumps(data, ensure_ascii=False)


def _steps(ci: dict, job: str) -> list[dict]:
    return ci["jobs"][job]["steps"]


def _step_text(step: dict) -> str:
    return _blob(step)


# ---- 做法 1 ----


def test_compose_only_defines_four_test_services(compose: dict) -> None:
    assert set(compose["services"]) == SERVICES


def test_compose_has_no_project_name(compose: dict) -> None:
    assert "name" not in compose


def test_compose_services_have_no_container_name(compose: dict) -> None:
    for name, svc in compose["services"].items():
        assert "container_name" not in svc, name


def test_compose_services_publish_no_ports(compose: dict) -> None:
    for name, svc in compose["services"].items():
        assert "ports" not in svc, name


# ---- 做法 3 ----


def test_test_service_uses_uv_python312_image(compose: dict) -> None:
    image = compose["services"]["test"]["image"]
    assert "uv" in image and "3.12" in image


def _mounts(svc: dict) -> list[dict]:
    out = []
    for v in svc.get("volumes", []):
        if isinstance(v, str):
            parts = v.split(":")
            out.append(
                {
                    "source": parts[0],
                    "target": parts[1] if len(parts) > 1 else None,
                    "ro": parts[-1] == "ro" if len(parts) > 2 else False,
                }
            )
        else:
            out.append(
                {
                    "source": v.get("source"),
                    "target": v.get("target"),
                    "ro": bool(v.get("read_only")),
                }
            )
    return out


def test_test_service_mounts_worktree_read_only(compose: dict) -> None:
    mounts = _mounts(compose["services"]["test"])
    repo = [m for m in mounts if m["source"] in (".", "./")]
    assert repo, "沒有把 worktree（.）掛進 test 服務"
    assert all(m["ro"] for m in repo)


def test_test_service_keeps_venv_and_uv_cache_in_named_volumes(compose: dict) -> None:
    svc = compose["services"]["test"]
    named = {
        m["target"] for m in _mounts(svc) if m["source"] and not m["source"].startswith((".", "/"))
    }
    env = svc.get("environment", {})
    if isinstance(env, list):
        env = dict(e.split("=", 1) for e in env)
    venv = env.get("UV_PROJECT_ENVIRONMENT")
    assert venv, "未設定 UV_PROJECT_ENVIRONMENT"
    assert any(venv.startswith(t) for t in named), "venv 不在 named volume"
    cache = env.get("UV_CACHE_DIR")
    assert cache and any(cache.startswith(t) for t in named), "uv 快取不在 named volume"
    assert set(compose.get("volumes", {})) >= {
        m["source"] for m in _mounts(svc) if m["target"] in named
    }


def test_test_service_syncs_frozen_then_runs_integration_pytest(compose: dict) -> None:
    svc = compose["services"]["test"]
    text = _blob([svc.get("entrypoint"), svc.get("command")])
    assert "uv sync --frozen" in text
    assert "pytest tests/integration" in text
    assert text.index("uv sync --frozen") < text.index("pytest tests/integration")


def test_test_service_does_not_use_host_uid(compose: dict) -> None:
    assert "HOST_UID" not in _blob(compose["services"]["test"])


def test_test_service_depends_on_the_three_services(compose: dict) -> None:
    dep = compose["services"]["test"].get("depends_on", {})
    assert set(dep) >= set(DEPS)


def test_test_service_receives_it_connection_variables(compose: dict) -> None:
    text = _blob(compose["services"]["test"].get("environment", {}))
    for key in ("IT_KAFKA_BOOTSTRAP", "IT_POSTGRES_HOST", "IT_POSTGRES_PORT", "IT_CLICKHOUSE_URL"):
        assert key in text, key


# ---- 做法 4 ----


def test_compose_does_not_mount_docker_socket(compose: dict, compose_ci: dict) -> None:
    for data in (compose, compose_ci):
        assert "docker.sock" not in _blob(data)


def test_compose_has_no_privileged_or_host_network(compose: dict) -> None:
    for name, svc in compose["services"].items():
        assert not svc.get("privileged"), name
        assert svc.get("network_mode") != "host", name


# ---- 做法 5 ----


def test_dependency_services_store_data_on_tmpfs(compose: dict) -> None:
    for name in DEPS:
        svc = compose["services"][name]
        has_tmpfs = bool(svc.get("tmpfs")) or any(
            isinstance(v, dict) and v.get("type") == "tmpfs" for v in svc.get("volumes", [])
        )
        assert has_tmpfs, name


@pytest.mark.parametrize(
    ("service", "var"),
    [
        ("kafka", "KAFKA_VERSION"),
        ("postgres", "POSTGRES_VERSION"),
        ("clickhouse", "CLICKHOUSE_VERSION"),
    ],
)
def test_dependency_image_version_is_required_env_variable(
    compose: dict, service: str, var: str
) -> None:
    assert "${" + var + ":?" in compose["services"][service]["image"]


# ---- 做法 2（移除 testcontainers）----


def test_pyproject_no_longer_depends_on_testcontainers() -> None:
    assert "testcontainers" not in (ROOT / "pyproject.toml").read_text()


# ---- 做法 10 ----


@pytest.mark.parametrize(
    ("service", "var"),
    [
        ("kafka", "IT_KAFKA_HOST_PORT"),
        ("postgres", "IT_POSTGRES_HOST_PORT"),
        ("clickhouse", "IT_CLICKHOUSE_HOST_PORT"),
    ],
)
def test_ci_override_binds_service_port_to_loopback(
    compose_ci: dict, service: str, var: str
) -> None:
    ports = [str(p) for p in compose_ci["services"][service]["ports"]]
    assert any(p.startswith("127.0.0.1:${" + var) for p in ports), ports


def test_env_example_declares_host_port_variables() -> None:
    text = (ROOT / ".env.example").read_text()
    for var in ("IT_KAFKA_HOST_PORT", "IT_POSTGRES_HOST_PORT", "IT_CLICKHOUSE_HOST_PORT"):
        assert re.search(rf"^{var}=", text, re.M), var


def test_ci_integration_job_brings_up_services_then_runs_coverage(ci: dict) -> None:
    texts = [_step_text(s) for s in _steps(ci, "integration")]
    joined = "\n".join(texts)
    assert "compose.ci.yaml" in joined
    pull = next(i for i, t in enumerate(texts) if re.search(r"compose.*\bpull\b", t))
    up = next(i for i, t in enumerate(texts) if "up -d --wait" in t and all(s in t for s in DEPS))
    cov = next(i for i, t in enumerate(texts) if "make coverage" in t)
    assert pull < up < cov


def test_ci_integration_job_points_it_variables_at_localhost(ci: dict) -> None:
    joined = _blob(ci["jobs"]["integration"])
    for key in ("IT_KAFKA_BOOTSTRAP", "IT_POSTGRES_HOST", "IT_POSTGRES_PORT", "IT_CLICKHOUSE_URL"):
        assert key in joined, key
    assert "127.0.0.1" in joined or "localhost" in joined


def test_ci_integration_job_uses_gcr_registry_mirror(ci: dict) -> None:
    joined = _blob(ci["jobs"]["integration"])
    assert "registry-mirrors" in joined and "mirror.gcr.io" in joined


def test_ci_no_longer_mentions_testcontainers() -> None:
    assert "TESTCONTAINERS" not in (ROOT / ".github/workflows/ci.yml").read_text()


# ---- 做法 11 ----


def test_ci_job_names_are_unchanged(ci: dict) -> None:
    assert ci["jobs"]["check"]["name"] == "Check"
    assert ci["jobs"]["integration"]["name"] == "Integration Test"


def test_ci_check_job_only_runs_make_check(ci: dict) -> None:
    joined = _blob(ci["jobs"]["check"])
    assert "make check" in joined
    assert "make coverage" not in joined
    assert "coverage_gate" not in joined


def test_ci_integration_job_runs_coverage_and_gate_only_for_pr_to_develop(ci: dict) -> None:
    steps = _steps(ci, "integration")
    cov = [s for s in steps if "make coverage" in _step_text(s)]
    gate = [s for s in steps if "coverage_gate.py" in _step_text(s)]
    assert len(cov) == 1 and gate
    for s in gate:
        cond = s.get("if", "")
        assert "pull_request" in cond and "develop" in cond


def test_ci_runs_integration_tests_once_per_event(ci: dict) -> None:
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert len(re.findall(r"make coverage", text)) == 1
    assert "pytest tests/integration" not in text


# ---- 做法 12 ----


def test_ci_uses_job_level_skip_not_paths_ignore(ci: dict) -> None:
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "paths-ignore" not in text
    on = ci.get("on", ci.get(True))
    for trigger in on.values():
        assert "paths" not in trigger and "paths-ignore" not in trigger


def test_ci_integration_first_step_diffs_changed_files(ci: dict) -> None:
    steps = _steps(ci, "integration")
    # checkout 之後第一個判斷步驟要用 git diff --name-only
    idx = next(i for i, s in enumerate(steps) if "git diff --name-only" in _step_text(s))
    assert all("uses" in s and "checkout" in s["uses"] for s in steps[:idx]), (
        "git diff 之前除了 checkout 不應有其他步驟"
    )
    text = _step_text(steps[idx])
    assert "github.event.before" in text
    for path in ("docs/", "tasks/", "reports/"):
        assert path in text, path


def test_ci_integration_later_steps_are_skippable_by_if(ci: dict) -> None:
    steps = _steps(ci, "integration")
    idx = next(i for i, s in enumerate(steps) if "git diff --name-only" in _step_text(s))
    later = steps[idx + 1 :]
    assert later
    for s in later:
        assert "if" in s, s.get("name")
    assert "if" not in ci["jobs"]["integration"], "job 層級 if 會讓 check 不出現"

"""驗收 init-exit-code（#66）：初始化各工具失敗時結束碼非 0 且 log 說明哪一步、原因；冪等重跑回 0。

每個情境在子行程跑工具的 main()，才看得到真正的結束碼；外部服務一律用 fake，不連網路。
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4]
COMPOSE = ROOT / "infra/docker-compose.yaml"

DRIVER = """
import importlib.util, sys
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("tool_under_test", path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
{setup}
mod.main()
"""

FAKE_ADMIN = """
from concurrent.futures import Future
from confluent_kafka import KafkaError, KafkaException
from radar.common.kafka.topics import ExistingTopic

def _future(exc=None):
    f = Future()
    if exc is None:
        f.set_result(None)
    else:
        f.set_exception(exc)
    return f

class FakeAdmin:
    def __init__(self, *a, **k):
        pass
    def create_topics(self, topics):
        return {t.topic: _future(__EXC__) for t in topics}
    def create_partitions(self, parts):
        return {p.topic: _future() for p in parts}
"""


def run_tool(
    tool: str, setup: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = {
        k: v for k, v in os.environ.items() if not k.startswith(("CONNECT_", "CLICKHOUSE_"))
    }
    full_env.update(env or {})
    code = DRIVER.format(setup=textwrap.indent(textwrap.dedent(setup), ""))
    return subprocess.run(
        [sys.executable, "-c", code, str(ROOT / "tools" / tool)],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=ROOT,
        timeout=60,
        check=False,
    )


def assert_failed_with_reason(proc: subprocess.CompletedProcess[str], step: str, reason: str):
    assert proc.returncode != 0, f"expected non-zero exit, got 0\n{proc.stderr}"
    lines = (proc.stdout + proc.stderr).splitlines()
    hits = [
        ln
        for ln in lines
        if ("CRITICAL" in ln or "ERROR" in ln) and step in ln.lower() and reason in ln
    ]
    assert hits, f"no single ERROR/CRITICAL log line naming step {step!r} and {reason!r}:\n" + (
        "\n".join(lines)
    )


# ---------- create_topics ----------

TOPIC_ENV = {"KAFKA_BOOTSTRAP_SERVERS": "unused:9092"}


def topics_setup(existing: str, create_exc: str = "None") -> str:
    return (
        FAKE_ADMIN.replace("__EXC__", create_exc)
        + f"""
mod.AdminClient = FakeAdmin
mod.fetch_existing = lambda admin, names: {existing}
"""
    )


def test_topics_admin_failure_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = topics_setup(
        "{}",
        'KafkaException(KafkaError(KafkaError._TRANSPORT, "broker down boom"))',
    )
    proc = run_tool("create_topics.py", setup, TOPIC_ENV)
    assert_failed_with_reason(proc, "topic", "broker down boom")


def test_topics_fetch_existing_failure_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = """
class Admin:
    def __init__(self, *a, **k):
        pass
mod.AdminClient = Admin
def boom(admin, names):
    raise RuntimeError("metadata timeout boom")
mod.fetch_existing = boom
"""
    proc = run_tool("create_topics.py", setup, TOPIC_ENV)
    assert_failed_with_reason(proc, "topic", "metadata timeout boom")


def test_topics_missing_spec_file_exits_nonzero_and_logs_step_and_reason(tmp_path: Path) -> None:
    setup = f"""
from pathlib import Path
mod.TOPICS_FILE = Path({str(tmp_path / "nope.yaml")!r})
"""
    proc = run_tool("create_topics.py", setup, TOPIC_ENV)
    assert_failed_with_reason(proc, "topic", "nope.yaml")


def test_topics_already_exist_race_exits_zero() -> None:
    setup = topics_setup(
        "{}",
        "KafkaException(KafkaError(KafkaError.TOPIC_ALREADY_EXISTS))",
    )
    proc = run_tool("create_topics.py", setup, TOPIC_ENV)
    assert proc.returncode == 0, proc.stderr


def test_topics_create_succeeds_exits_zero() -> None:
    proc = run_tool("create_topics.py", topics_setup("{}"), TOPIC_ENV)
    assert proc.returncode == 0, proc.stderr


def test_topics_all_up_to_date_exits_zero() -> None:
    setup = """
class Admin:
    def __init__(self, *a, **k):
        pass
mod.AdminClient = Admin
from radar.common.kafka.topics import TopicPlan
mod.plan_changes = lambda specs, existing: TopicPlan(create=[], add_partitions={}, alter_config={})
mod.fetch_existing = lambda admin, names: {}
"""
    proc = run_tool("create_topics.py", setup, TOPIC_ENV)
    assert proc.returncode == 0, proc.stderr


# ---------- migrate_clickhouse ----------

CH_ENV = {
    "CLICKHOUSE_URL": "http://ch.invalid:8123",
    "CLICKHOUSE_USER": "u",
    "CLICKHOUSE_PASSWORD": "p",
}


def ch_setup(handler_body: str) -> str:
    return f"""
import httpx2
from radar.common.clickhouse import ClickHouseClient as _Real
def handler(request):
{textwrap.indent(textwrap.dedent(handler_body), "    ")}
mod.ClickHouseClient = lambda settings: _Real(settings, transport=httpx2.MockTransport(handler))
"""


def test_clickhouse_server_error_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = ch_setup('return httpx2.Response(500, text="Code 999 keeper boom")')
    proc = run_tool("migrate_clickhouse.py", setup, CH_ENV)
    assert_failed_with_reason(proc, "clickhouse", "keeper boom")


def test_clickhouse_ddl_failure_midway_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = ch_setup(
        """
        body = request.content.decode()
        if "SELECT version" in body:
            return httpx2.Response(200, text="")
        if body.lstrip().upper().startswith("CREATE TABLE IF NOT EXISTS"):
            if "schema_migrations" in body or "applied_at" in body:
                return httpx2.Response(200, text="")
        return httpx2.Response(500, text="DDL syntax boom")
        """
    )
    proc = run_tool("migrate_clickhouse.py", setup, CH_ENV)
    assert_failed_with_reason(proc, "clickhouse", "DDL syntax boom")


def test_clickhouse_bad_migration_dir_exits_nonzero_and_logs_step_and_reason(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "migrations"
    bad.mkdir()
    (bad / "not_a_migration.sql").write_text("SELECT 1")
    setup = f"""
from pathlib import Path
mod.MIGRATIONS_DIR = Path({str(bad)!r})
""" + ch_setup('return httpx2.Response(200, text="")')
    proc = run_tool("migrate_clickhouse.py", setup, CH_ENV)
    assert_failed_with_reason(proc, "clickhouse", "not_a_migration")


def test_clickhouse_already_migrated_exits_zero() -> None:
    setup = """
import re
from pathlib import Path
versions = sorted(
    int(re.match(r"(\\d+)_", p.name).group(1)) for p in mod.MIGRATIONS_DIR.glob("*.sql")
)
""" + ch_setup(
        """
        body = request.content.decode()
        if "SELECT version" in body:
            return httpx2.Response(200, text="\\n".join(str(v) for v in versions))
        if body.lstrip().upper().startswith("CREATE TABLE IF NOT EXISTS"):
            return httpx2.Response(200, text="")
        return httpx2.Response(500, text="must not run any migration again")
        """
    )
    proc = run_tool("migrate_clickhouse.py", setup, CH_ENV)
    assert proc.returncode == 0, proc.stderr


# ---------- register_connector ----------

CONNECT_ENV = {"CONNECT_URL": "http://connect.invalid:8083", "CONNECT_READY_TIMEOUT_S": "1"}


def connector_setup(handler_body: str, fake_spec: bool = True) -> str:
    spec = (
        "from radar.common.kafka.connect import ConnectorSpec\n"
        "mod.load_connector_spec = lambda path, env: ConnectorSpec('radar-cdc', {})\n"
        if fake_spec
        else ""
    )
    return (
        f"""
import httpx2
def handler(request):
{textwrap.indent(textwrap.dedent(handler_body), "    ")}
_Client = httpx2.Client
mod.httpx2.Client = lambda **kw: _Client(transport=httpx2.MockTransport(handler), **kw)
"""
        + spec
    )


def test_connector_put_rejected_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = connector_setup(
        """
        if request.method == "PUT":
            return httpx2.Response(500, text="plugin boom")
        return httpx2.Response(200, json={})
        """
    )
    proc = run_tool("register_connector.py", setup, CONNECT_ENV)
    assert_failed_with_reason(proc, "connector", "plugin boom")


def test_connector_task_failed_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = connector_setup(
        """
        if request.method == "PUT":
            return httpx2.Response(201, json={})
        if request.url.path.endswith("/status"):
            return httpx2.Response(200, json={
                "connector": {"state": "RUNNING"}, "tasks": [{"state": "FAILED"}]})
        return httpx2.Response(200, json={})
        """
    )
    proc = run_tool("register_connector.py", setup, CONNECT_ENV)
    assert_failed_with_reason(proc, "connector", "FAILED")


def test_connector_connect_unreachable_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = connector_setup(
        """
        raise httpx2.ConnectError("connection refused boom")
        """
    )
    proc = run_tool("register_connector.py", setup, CONNECT_ENV)
    assert_failed_with_reason(proc, "connect", "not ready")


def test_connector_missing_env_var_exits_nonzero_and_logs_step_and_reason() -> None:
    setup = connector_setup("return httpx2.Response(200, json={})", fake_spec=False)
    env = dict(CONNECT_ENV)
    proc = run_tool("register_connector.py", setup, env)
    # radar-cdc.json 引用的環境變數在測試環境未設定
    assert_failed_with_reason(proc, "connector", "missing env vars")


@pytest.mark.parametrize("put_status", [200, 201])
def test_connector_already_registered_or_created_exits_zero(put_status: int) -> None:
    setup = connector_setup(
        f"""
        if request.method == "PUT":
            return httpx2.Response({put_status}, json={{}})
        if request.url.path.endswith("/status"):
            return httpx2.Response(200, json={{
                "connector": {{"state": "RUNNING"}}, "tasks": [{{"state": "RUNNING"}}]}})
        return httpx2.Response(200, json={{}})
        """
    )
    proc = run_tool("register_connector.py", setup, CONNECT_ENV)
    assert proc.returncode == 0, proc.stderr


# ---------- compose init 服務 ----------


def init_command() -> str:
    cfg = yaml.safe_load(COMPOSE.read_text())
    cmd = cfg["services"]["init"]["command"]
    return cmd if isinstance(cmd, str) else " ".join(cmd)


def test_init_command_runs_steps_in_order_failing_fast() -> None:
    cmd = init_command()
    steps = ["alembic upgrade head", "create_topics.py", "migrate_clickhouse.py"]
    steps.append("register_connector.py")
    positions = [cmd.index(s) for s in steps]
    assert positions == sorted(positions)
    assert "||" not in cmd and ";" not in cmd
    for a, b in zip(positions, positions[1:], strict=False):
        assert "&&" in cmd[a:b], "steps must be chained with && so a failure stops init"


def test_init_command_does_not_swallow_the_exit_code() -> None:
    cmd = init_command()
    for bad in ("|| true", "|| exit 0", "exit 255", "; true"):
        assert bad not in cmd

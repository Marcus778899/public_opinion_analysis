import json
from pathlib import Path

import httpx2
import pytest

from radar.common.kafka import connect
from radar.common.kafka.connect import (
    ConnectError,
    ConnectorConfigError,
    ConnectorSpec,
    ConnectorStatus,
    get_status,
    load_connector_spec,
    put_connector,
    wait_until_ready,
    wait_until_running,
)

REPO_CONNECTOR = Path(__file__).resolve().parents[4] / "infra/debezium/radar-cdc.json"
SPEC = ConnectorSpec(name="radar-cdc", config={"a": "1"})


def client_with(handler) -> httpx2.Client:
    return httpx2.Client(base_url="http://connect:8083", transport=httpx2.MockTransport(handler))


def write_spec(tmp_path: Path, body: object) -> Path:
    path = tmp_path / "c.json"
    path.write_text(json.dumps(body))
    return path


def test_load_connector_spec_substitutes_env_vars(tmp_path):
    path = write_spec(
        tmp_path, {"name": "c", "config": {"host": "${HOST}", "url": "http://${HOST}:${PORT}/x"}}
    )

    spec = load_connector_spec(path, {"HOST": "pg", "PORT": "5432"})

    assert spec == ConnectorSpec(name="c", config={"host": "pg", "url": "http://pg:5432/x"})


def test_load_connector_spec_missing_vars_lists_all_names(tmp_path):
    path = write_spec(tmp_path, {"name": "c", "config": {"a": "${B_VAR}", "b": "${A_VAR}"}})

    with pytest.raises(ConnectorConfigError, match="A_VAR, B_VAR"):
        load_connector_spec(path, {})


def test_load_connector_spec_without_name_raises(tmp_path):
    path = write_spec(tmp_path, {"config": {}})

    with pytest.raises(ConnectorConfigError):
        load_connector_spec(path, {})


def test_load_connector_spec_invalid_json_raises(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("{not json")

    with pytest.raises(ConnectorConfigError):
        load_connector_spec(path, {})


def test_load_connector_spec_repo_file_uses_content_id_and_rewrites_deletes():
    env = {
        v: "x" for v in ("CDC_DATABASE_HOST", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
    }
    env["CDC_REGISTRY_URL"] = "http://apicurio:8080/apis/registry/v3"

    config = load_connector_spec(REPO_CONNECTOR, env).config

    # 設計文件 6.2：ClickHouse 以 contentId 查 schema；3.x 的刪除改寫設定名稱
    assert config["key.converter.apicurio.registry.use-id"] == "contentId"
    assert config["value.converter.apicurio.registry.use-id"] == "contentId"
    assert config["transforms.unwrap.delete.tombstone.handling.mode"] == "rewrite"
    assert config["table.include.list"] == "public.posts,public.comments"
    assert not any(k.endswith(".delete.handling.mode") for k in config)


def test_wait_until_ready_retries_connection_error_then_returns(monkeypatch):
    monkeypatch.setattr(connect.time, "sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) < 3:
            raise httpx2.ConnectError("refused")
        return httpx2.Response(200, json={})

    wait_until_ready(client_with(handler), timeout_s=60)

    assert len(calls) == 3


def test_wait_until_ready_timeout_raises(monkeypatch):
    monkeypatch.setattr(connect.time, "sleep", lambda _: None)
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(connect.time, "monotonic", lambda: next(clock))

    with pytest.raises(ConnectError, match="not ready"):
        wait_until_ready(client_with(lambda r: httpx2.Response(503)), timeout_s=30)


def test_put_connector_created_returns_true():
    seen = {}

    def handler(request):
        seen["method"], seen["path"] = request.method, request.url.path
        seen["body"] = json.loads(request.content)
        return httpx2.Response(201, json={})

    assert put_connector(client_with(handler), SPEC) is True
    assert seen == {"method": "PUT", "path": "/connectors/radar-cdc/config", "body": {"a": "1"}}


def test_put_connector_updated_returns_false():
    assert put_connector(client_with(lambda r: httpx2.Response(200, json={})), SPEC) is False


def test_put_connector_bad_request_raises_with_body():
    client = client_with(lambda r: httpx2.Response(400, text="Connector config is invalid"))

    with pytest.raises(ConnectError, match="config is invalid"):
        put_connector(client, SPEC)


def test_get_status_parses_connector_and_task_states():
    body = {"connector": {"state": "RUNNING"}, "tasks": [{"id": 0, "state": "FAILED"}]}

    status = get_status(client_with(lambda r: httpx2.Response(200, json=body)), "radar-cdc")

    assert status == ConnectorStatus(connector_state="RUNNING", task_states=["FAILED"])


def test_get_status_unknown_connector_raises():
    with pytest.raises(ConnectError, match="404"):
        get_status(client_with(lambda r: httpx2.Response(404, text="not found")), "x")


def test_connector_status_all_running_is_running():
    assert ConnectorStatus("RUNNING", ["RUNNING", "RUNNING"]).is_running


def test_connector_status_failed_task_is_not_running():
    assert not ConnectorStatus("RUNNING", ["RUNNING", "FAILED"]).is_running


def test_connector_status_no_tasks_is_not_running():
    assert not ConnectorStatus("RUNNING", []).is_running


def status_sequence(*bodies):
    it = iter(bodies)
    return client_with(lambda r: httpx2.Response(200, json=next(it)))


def body(connector: str, *tasks: str) -> dict:
    return {
        "connector": {"state": connector},
        "tasks": [{"id": i, "state": s} for i, s in enumerate(tasks)],
    }


def test_wait_until_running_polls_until_tasks_start(monkeypatch):
    monkeypatch.setattr(connect.time, "sleep", lambda _: None)
    client = status_sequence(
        body("RUNNING"), body("RUNNING", "UNASSIGNED"), body("RUNNING", "RUNNING")
    )

    assert wait_until_running(client, "c", timeout_s=60).is_running


def test_wait_until_running_failed_task_raises_immediately(monkeypatch):
    monkeypatch.setattr(connect.time, "sleep", lambda _: None)

    with pytest.raises(ConnectError, match="failed"):
        wait_until_running(status_sequence(body("RUNNING", "FAILED")), "c", timeout_s=60)


def test_wait_until_running_status_404_right_after_create_keeps_polling(monkeypatch):
    monkeypatch.setattr(connect.time, "sleep", lambda _: None)
    responses = iter(
        [
            httpx2.Response(404, json={"error_code": 404, "message": "No status found"}),
            httpx2.Response(200, json=body("RUNNING", "RUNNING")),
        ]
    )

    status = wait_until_running(client_with(lambda r: next(responses)), "c", timeout_s=60)

    assert status.is_running


def test_wait_until_running_status_404_until_timeout_raises(monkeypatch):
    monkeypatch.setattr(connect.time, "sleep", lambda _: None)
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(connect.time, "monotonic", lambda: next(clock))
    client = client_with(lambda r: httpx2.Response(404, text="not found"))

    with pytest.raises(ConnectError, match="not running"):
        wait_until_running(client, "c", timeout_s=30)


def test_wait_until_running_timeout_raises(monkeypatch):
    monkeypatch.setattr(connect.time, "sleep", lambda _: None)
    clock = iter(range(0, 1000, 10))
    monkeypatch.setattr(connect.time, "monotonic", lambda: next(clock))
    client = client_with(lambda r: httpx2.Response(200, json=body("RUNNING")))

    with pytest.raises(ConnectError, match="not running"):
        wait_until_running(client, "c", timeout_s=30)

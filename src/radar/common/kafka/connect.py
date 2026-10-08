"""註冊 Debezium connector（開發規格 7.9）；設定檔以 ${VAR} 引用環境變數。"""

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import httpx2

_VAR = re.compile(r"\$\{([A-Z0-9_]+)\}")
_RUNNING = "RUNNING"
_FAILED = "FAILED"


class ConnectorConfigError(ValueError):
    """設定檔格式錯誤或引用了未設定的環境變數。"""


class ConnectError(RuntimeError):
    """Kafka Connect REST API 回應非預期的狀態碼，或逾時仍未就緒。"""


class ConnectorNotFoundError(ConnectError):
    """查狀態時回 404：connector 不存在，或剛建立、狀態尚未產生。"""


@dataclass(frozen=True)
class ConnectorSpec:
    name: str
    config: dict[str, str]


@dataclass(frozen=True)
class ConnectorStatus:
    connector_state: str
    task_states: list[str]

    @property
    def is_running(self) -> bool:
        return (
            self.connector_state == _RUNNING
            and bool(self.task_states)
            and all(s == _RUNNING for s in self.task_states)
        )


def load_connector_spec(path: Path, env: Mapping[str, str]) -> ConnectorSpec:
    try:
        raw = json.loads(path.read_text())
        name, config = raw["name"], raw["config"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise ConnectorConfigError(f"{path}: expected {{'name', 'config'}}: {e!r}") from e
    if not isinstance(name, str) or not isinstance(config, dict):
        raise ConnectorConfigError(f"{path}: name must be a string and config an object")

    missing: set[str] = set()

    def substitute(match: re.Match[str]) -> str:
        var = match.group(1)
        if var not in env:
            missing.add(var)
            return ""
        return env[var]

    resolved = {str(k): _VAR.sub(substitute, str(v)) for k, v in config.items()}
    if missing:
        raise ConnectorConfigError(f"{path}: missing env vars: {', '.join(sorted(missing))}")
    return ConnectorSpec(name=name, config=resolved)


def wait_until_ready(client: httpx2.Client, timeout_s: float, poll_s: float = 3.0) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            if client.get("/").status_code == 200:
                return
        except httpx2.TransportError:
            pass
        if time.monotonic() >= deadline:
            raise ConnectError(f"kafka connect not ready after {timeout_s}s")
        time.sleep(poll_s)


def put_connector(client: httpx2.Client, spec: ConnectorSpec) -> bool:
    """PUT /connectors/<name>/config（冪等）；回傳是否為新建立。"""
    resp = client.put(f"/connectors/{spec.name}/config", json=spec.config)
    if resp.status_code == 201:
        return True
    if resp.status_code == 200:
        return False
    raise ConnectError(f"put connector {spec.name} failed: {resp.status_code} {resp.text}")


def get_status(client: httpx2.Client, name: str) -> ConnectorStatus:
    resp = client.get(f"/connectors/{name}/status")
    if resp.status_code == 404:
        raise ConnectorNotFoundError(f"get status {name} failed: 404 {resp.text}")
    if resp.status_code != 200:
        raise ConnectError(f"get status {name} failed: {resp.status_code} {resp.text}")
    body = resp.json()
    return ConnectorStatus(
        connector_state=body["connector"]["state"],
        task_states=[t["state"] for t in body.get("tasks", [])],
    )


def wait_until_running(
    client: httpx2.Client, name: str, timeout_s: float, poll_s: float = 2.0
) -> ConnectorStatus:
    """PUT 成功只代表設定被接受；連不上 PG、publication 不存在要等 task 啟動才會失敗。"""
    # NOTE: PUT 建立後狀態是非同步產生的，剛建立時查狀態會先回 404
    deadline = time.monotonic() + timeout_s
    while True:
        status: ConnectorStatus | str
        try:
            status = get_status(client, name)
        except ConnectorNotFoundError:
            status = "status not found yet"
        else:
            if status.is_running:
                return status
            if _FAILED in [status.connector_state, *status.task_states]:
                raise ConnectError(f"connector {name} failed: {status}")
        if time.monotonic() >= deadline:
            raise ConnectError(f"connector {name} not running after {timeout_s}s: {status}")
        time.sleep(poll_s)

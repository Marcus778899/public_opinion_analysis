"""驗收 connect-resilience（開發規格 7.30 B、D）：wait_until_ready 與 wait_until_running 的重啟。

介面：wait_until_running(client, name, timeout_s, poll_s=2.0, *, restart_limit=0,
restart_grace_s=15.0)；重啟走 POST /connectors/<name>/restart。
"""

import importlib.util
import sys
from pathlib import Path

import httpx2
import pytest

from radar.common.kafka import connect
from radar.common.kafka.connect import ConnectError, wait_until_ready, wait_until_running

ROOT = Path(__file__).resolve().parents[4]
BASE = "http://connect:8083"


class Clock:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.now = 0.0
        monkeypatch.setattr(connect.time, "monotonic", lambda: self.now)
        monkeypatch.setattr(connect.time, "sleep", self.sleep)

    def sleep(self, s: float) -> None:
        self.now += s


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    return Clock(monkeypatch)


def client(handler) -> httpx2.Client:
    return httpx2.Client(base_url=BASE, transport=httpx2.MockTransport(handler))


def status_json(connector: str, *tasks: str) -> dict:
    return {
        "connector": {"state": connector},
        "tasks": [{"id": i, "state": s} for i, s in enumerate(tasks)],
    }


# ---------- wait_until_ready ----------


def test_wait_until_ready_polls_health_endpoint(clock: Clock) -> None:
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        paths.append(request.url.path)
        return httpx2.Response(200)

    wait_until_ready(client(handler), timeout_s=60)
    assert paths == ["/health"]


def test_wait_until_ready_root_ok_but_health_503_keeps_waiting_until_timeout(clock: Clock) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200 if request.url.path == "/" else 503)

    with pytest.raises(ConnectError, match="not ready"):
        wait_until_ready(client(handler), timeout_s=30)


def test_wait_until_ready_health_recovers_after_503_returns(clock: Clock) -> None:
    codes = iter([503, 503, 200])
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        return httpx2.Response(next(codes))

    wait_until_ready(client(handler), timeout_s=60)
    assert seen == ["/health"] * 3


def test_wait_until_ready_connection_error_then_health_ok_returns(clock: Clock) -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx2.ConnectError("refused")
        return httpx2.Response(200)

    wait_until_ready(client(handler), timeout_s=60)
    assert calls["n"] == 2


# ---------- wait_until_running 重啟 ----------


class FakeConnect:
    """status 依「已重啟幾次」查表；超出表長沿用最後一個。"""

    def __init__(self, by_restarts: list[dict]) -> None:
        self.by_restarts = by_restarts
        self.restarts: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST" and request.url.path.endswith("/restart"):
            self.restarts.append(request)
            return httpx2.Response(204)
        n = min(len(self.restarts), len(self.by_restarts) - 1)
        return httpx2.Response(200, json=self.by_restarts[n])


FAILED = status_json("RUNNING", "FAILED")
RUNNING = status_json("RUNNING", "RUNNING")


def test_wait_until_running_failed_then_one_restart_running_succeeds(clock: Clock) -> None:
    fake = FakeConnect([FAILED, RUNNING])

    status = wait_until_running(client(fake), "radar-cdc", 60, restart_limit=2)

    assert status.is_running
    assert len(fake.restarts) == 1
    assert fake.restarts[0].url.path == "/connectors/radar-cdc/restart"
    assert fake.restarts[0].url.params["includeTasks"] == "true"
    assert fake.restarts[0].url.params["onlyFailed"] == "true"


def test_wait_until_running_still_failed_after_limit_raises_after_sending_restarts(
    clock: Clock,
) -> None:
    fake = FakeConnect([FAILED])

    with pytest.raises(ConnectError, match="FAILED"):
        wait_until_running(client(fake), "radar-cdc", 120, restart_limit=2, restart_grace_s=10)

    assert len(fake.restarts) == 2


def test_wait_until_running_failed_within_grace_is_not_judged(clock: Clock) -> None:
    # 重啟後 grace 內仍讀到舊的 FAILED：不再重啟、不判失敗，之後恢復就成功
    seq = [FAILED, FAILED, FAILED, RUNNING]
    reads = {"n": 0}
    restarts: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            restarts.append(request)
            return httpx2.Response(204)
        body = seq[min(reads["n"], len(seq) - 1)]
        reads["n"] += 1
        return httpx2.Response(200, json=body)

    status = wait_until_running(
        client(handler), "radar-cdc", 120, restart_limit=1, restart_grace_s=30
    )

    assert status.is_running
    assert len(restarts) == 1


def test_wait_until_running_restart_limit_default_zero_fails_without_restart(clock: Clock) -> None:
    fake = FakeConnect([FAILED])

    with pytest.raises(ConnectError, match="FAILED"):
        wait_until_running(client(fake), "radar-cdc", 60)

    assert fake.restarts == []


def test_wait_until_running_restart_limit_zero_explicit_fails_without_restart(
    clock: Clock,
) -> None:
    fake = FakeConnect([FAILED])

    with pytest.raises(ConnectError):
        wait_until_running(client(fake), "radar-cdc", 60, restart_limit=0)

    assert fake.restarts == []


def test_wait_until_running_total_time_still_bounded_by_timeout(clock: Clock) -> None:
    fake = FakeConnect([FAILED])

    with pytest.raises(ConnectError):
        wait_until_running(client(fake), "radar-cdc", 30, restart_limit=5, restart_grace_s=1000)

    assert len(fake.restarts) >= 1
    assert clock.now <= 30 + 5


def test_wait_until_running_restart_request_error_propagates(clock: Clock) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.method == "POST":
            return httpx2.Response(500, text="restart boom")
        return httpx2.Response(200, json=FAILED)

    with pytest.raises(ConnectError, match="restart boom"):
        wait_until_running(client(handler), "radar-cdc", 60, restart_limit=2)


def test_wait_until_running_healthy_from_start_sends_no_restart(clock: Clock) -> None:
    fake = FakeConnect([RUNNING])

    assert wait_until_running(client(fake), "radar-cdc", 60, restart_limit=2).is_running
    assert fake.restarts == []


# ---------- tools/register_connector.py 常數 ----------


def load_tool():
    spec = importlib.util.spec_from_file_location(
        "register_connector_under_test", ROOT / "tools" / "register_connector.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_register_connector_restart_constants() -> None:
    mod = load_tool()
    assert mod.TASK_RESTART_LIMIT == 2
    assert mod.TASK_RESTART_GRACE_S == 15.0
    assert mod.RUNNING_TIMEOUT_S == 60.0

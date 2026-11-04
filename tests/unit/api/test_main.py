import pytest

from radar.api import main as api_main
from radar.common.log import log


def test_exit_for_restart_closes_log_before_exit_70(monkeypatch: pytest.MonkeyPatch):
    order: list[object] = []
    monkeypatch.setattr(log, "close", lambda *a, **k: order.append("close"), raising=False)
    monkeypatch.setattr(api_main.os, "_exit", lambda code: order.append(code))

    api_main.exit_for_restart()

    assert order == ["close", 70]

"""xdist 平行執行時的協調：全域重置每次測試只做一次（開發規格 7.26 平行執行的隔離）。"""

import fcntl
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest


def worker_id() -> str:
    """xdist 的 worker id（gw0…）；沒有平行時為 main。"""
    return os.environ.get("PYTEST_XDIST_WORKER", "main")


def run_once(key: str, action: Callable[[], None], root: Path | None = None) -> None:
    """同一次測試的所有 worker 只有第一個會執行 action，其餘等它做完。

    NOTE: pytest_sessionstart 只在 initial conftest 觸發，直接跑 `pytest` 時不會；
    改用 flock，不論從哪個入口進來，worker 在第一個測試前都會等到重置完成。
    """
    run_id = os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if run_id is None:
        action()
        return
    directory = (root or Path(tempfile.gettempdir())) / f"radar-it-{run_id}"
    directory.mkdir(exist_ok=True)
    done, failed = directory / f"{key}.done", directory / f"{key}.failed"
    with (directory / f"{key}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if failed.exists():
            pytest.exit(f"其他 worker 的 {key} 重置已失敗", returncode=2)
        if done.exists():
            return
        try:
            action()
        except BaseException:
            failed.touch()
            raise
        done.touch()

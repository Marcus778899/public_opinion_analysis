"""階段 2 的端到端流程：PG → Debezium → Kafka（Avro + Apicurio）→ ClickHouse。"""

import subprocess
import time
from contextlib import contextmanager

import httpx2

from radar.common.kafka.connect import ConnectError, ConnectorStatus, get_status
from tests.e2e.conftest import CONNECT_URL, clickhouse_rows, post_row, wait_until
from tests.e2e.test_pipeline import COMPOSE, new_post


def history(clickhouse, post_id: str) -> list[list[str]]:
    return clickhouse_rows(
        clickhouse,
        f"SELECT push_count, op FROM posts_history WHERE post_id = '{post_id}' ORDER BY lsn",
    )


def test_new_post_reaches_posts_latest(fake_ptt, db, clickhouse, board):
    post_id = new_post(fake_ptt, board)
    wait_until(lambda: post_row(db, post_id), timeout_s=60)

    rows = wait_until(
        lambda: clickhouse_rows(
            clickhouse,
            f"SELECT board, push_count FROM posts_latest FINAL WHERE post_id = '{post_id}'",
        ),
        timeout_s=60,
    )

    assert rows == [[board, "0"]]


def test_push_count_changes_are_recorded_in_history(fake_ptt, db, clickhouse, board):
    post_id = new_post(fake_ptt, board)
    wait_until(lambda: history(clickhouse, post_id), timeout_s=90)

    fake_ptt.post(f"/_control/posts/{post_id}/comments", json={"pushes": 5, "boos": 2})

    rows = wait_until(
        lambda: (h := history(clickhouse, post_id)) and h[-1][0] == "5" and h, timeout_s=90
    )
    assert rows[0] == ["0", "c"]
    assert rows[-1] == ["5", "u"]


def test_comments_reach_clickhouse_with_board(fake_ptt, db, clickhouse, board):
    post_id = new_post(fake_ptt, board)
    wait_until(lambda: post_row(db, post_id), timeout_s=60)
    fake_ptt.post(f"/_control/posts/{post_id}/comments", json={"pushes": 3, "boos": 0})

    rows = wait_until(
        lambda: (
            (
                r := clickhouse_rows(
                    clickhouse,
                    f"SELECT board, type FROM comments_latest FINAL WHERE post_id = '{post_id}'",
                )
            )
            and len(r) == 3
            and r
        ),
        timeout_s=90,
    )

    assert rows == [[board, "push"]] * 3


def test_unchanged_recrawl_produces_no_cdc_event(fake_ptt, db, clickhouse, board):
    post_id = new_post(fake_ptt, board)
    before = wait_until(lambda: history(clickhouse, post_id), timeout_s=90)

    time.sleep(30)  # e2e 的重爬間隔已縮短，這段時間內會重爬數次，但內容沒變

    assert history(clickhouse, post_id) == before


def comment_users(clickhouse, post_id: str) -> list[list[str]]:
    return clickhouse_rows(
        clickhouse,
        f"SELECT floor, user_id FROM comments_latest FINAL WHERE post_id = '{post_id}' "
        "ORDER BY floor",
    )


def test_deleted_comment_shifts_floors_in_clickhouse(fake_ptt, db, clickhouse, board):
    post_id = new_post(fake_ptt, board)
    wait_until(lambda: post_row(db, post_id), timeout_s=60)
    fake_ptt.post(f"/_control/posts/{post_id}/comments", json={"pushes": 3, "boos": 0})
    wait_until(lambda: len(comment_users(clickhouse, post_id)) == 3, timeout_s=90)

    fake_ptt.delete(f"/_control/posts/{post_id}/comments/2")

    rows = wait_until(
        lambda: (r := comment_users(clickhouse, post_id)) and len(r) == 2 and r, timeout_s=90
    )
    assert rows == [["1", "user1"], ["2", "user3"]]


# --- #31：Apicurio 停機時的 CDC（開發規格 7.16）---

CONNECTOR = "radar-cdc"
# 修正前 converter 快取的期限（apicurio.registry.check-period-ms 預設 30 秒）
OLD_CHECK_PERIOD_S = 30
# infra/debezium/radar-cdc.json 的 heartbeat.interval.ms
HEARTBEAT_INTERVAL_S = 60


def compose(*args: str) -> None:
    subprocess.run([*COMPOSE, *args], check=True, capture_output=True)


def connector_status() -> ConnectorStatus | None:
    try:
        with httpx2.Client(base_url=CONNECT_URL, timeout=5) as client:
            return get_status(client, CONNECTOR)
    except (ConnectError, httpx2.HTTPError):
        return None


def in_posts_latest(clickhouse, post_id: str) -> bool:
    sql = f"SELECT count() FROM posts_latest FINAL WHERE post_id = '{post_id}'"
    return clickhouse_rows(clickhouse, sql) == [["1"]]


@contextmanager
def registry_outage():
    """停掉 Apicurio；結束時一定恢復，並等 connector 回到 RUNNING，避免影響後續測試。"""
    compose("stop", "apicurio")
    try:
        yield
    finally:
        compose("start", "apicurio")
        # NOTE: 不呼叫 Connect 的重啟 API；task 若已失敗，要由 cdc-watchdog 重啟
        wait_until(
            lambda: (s := connector_status()) is not None and s.is_running,
            timeout_s=180,
            interval_s=5,
        )


def warm_up_converter_cache(fake_ptt, clickhouse, board: str) -> None:
    """讓 posts、comments、heartbeat 的 schema 都進 converter 快取。"""
    # NOTE: task 重啟會清空快取，且 heartbeat 要距離上次超過間隔、有新事件時才送（開發規格 7.16）
    post_id = new_post(fake_ptt, board)
    fake_ptt.post(f"/_control/posts/{post_id}/comments", json={"pushes": 1, "boos": 0})
    wait_until(lambda: comment_users(clickhouse, post_id), timeout_s=90)
    time.sleep(HEARTBEAT_INTERVAL_S + 5)
    post_id = new_post(fake_ptt, board)
    wait_until(lambda: in_posts_latest(clickhouse, post_id), timeout_s=90)


def test_registry_outage_longer_than_old_cache_period_keeps_cdc_flowing(
    fake_ptt, db, clickhouse, board
):
    warm_up_converter_cache(fake_ptt, clickhouse, board)

    with registry_outage():
        time.sleep(OLD_CHECK_PERIOD_S + 10)
        post_id = new_post(fake_ptt, board)

        wait_until(lambda: in_posts_latest(clickhouse, post_id), timeout_s=90)
        status = connector_status()
        assert status is not None and status.is_running


def test_failed_task_after_connect_restart_during_outage_recovers_without_manual_restart(
    fake_ptt, db, clickhouse, board
):
    with registry_outage():
        compose("restart", "connect")
        post_id = new_post(fake_ptt, board)
        wait_until(lambda: post_row(db, post_id), timeout_s=60)
        # Connect 重啟後快取是空的，新事件要向 Apicurio 註冊 schema，task 因此失敗
        wait_until(
            lambda: (s := connector_status()) is not None and s.is_failed,
            timeout_s=180,
            interval_s=2,
        )

    wait_until(lambda: in_posts_latest(clickhouse, post_id), timeout_s=120, interval_s=5)

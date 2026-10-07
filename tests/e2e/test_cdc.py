"""階段 2 的端到端流程：PG → Debezium → Kafka（Avro + Apicurio）→ ClickHouse。"""

import time

from tests.e2e.conftest import clickhouse_rows, post_row, wait_until
from tests.e2e.test_pipeline import new_post


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
                    clickhouse, f"SELECT board, type FROM comments WHERE post_id = '{post_id}'"
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

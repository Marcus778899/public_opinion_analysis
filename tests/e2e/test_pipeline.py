"""階段 1 的端到端流程：API → Scheduler → 爬蟲 → Ingest → PG，PTT 由假伺服器取代。"""

import subprocess
import time

from tests.e2e.conftest import post_row, wait_until

COMPOSE = [
    "docker", "compose", "-f", "infra/docker-compose.yaml",
    "-f", "infra/docker-compose.e2e.yaml", "--env-file", ".env",
]  # fmt: skip


def new_post(fake_ptt, board: str, title: str = "[測試] 端到端") -> str:
    response = fake_ptt.post("/_control/posts", json={"board": board, "title": title})
    response.raise_for_status()
    return response.json()["post_id"]


def test_new_board_is_scheduled_and_post_flows_into_postgres(fake_ptt, db, board):
    post_id = new_post(fake_ptt, board)

    # 看板新增後最多 30 秒同步，新計時器會立刻派發一次列表任務
    row = wait_until(lambda: post_row(db, post_id), timeout_s=60)

    assert (row.push_count, row.boo_count, row.is_deleted) == (0, 0, False)


def test_new_comments_update_push_count_on_recrawl(fake_ptt, db, board):
    post_id = new_post(fake_ptt, board)
    wait_until(lambda: post_row(db, post_id), timeout_s=60)

    fake_ptt.post(f"/_control/posts/{post_id}/comments", json={"pushes": 5, "boos": 2})

    row = wait_until(lambda: (r := post_row(db, post_id)) and r.push_count == 5 and r, timeout_s=60)
    assert row.boo_count == 2


def test_deleted_post_is_marked(fake_ptt, db, board):
    post_id = new_post(fake_ptt, board)
    wait_until(lambda: post_row(db, post_id), timeout_s=60)

    fake_ptt.delete(f"/_control/posts/{post_id}")

    wait_until(lambda: (r := post_row(db, post_id)) and r.is_deleted, timeout_s=60)


def test_disabled_board_stops_being_crawled(api, fake_ptt, db, board):
    first = new_post(fake_ptt, board)
    wait_until(lambda: post_row(db, first), timeout_s=60)

    api.patch(f"/boards/{board}", json={"enabled": False}).raise_for_status()
    time.sleep(35)  # 等 Scheduler 同步（30 秒一次）移除計時器
    later = new_post(fake_ptt, board)
    time.sleep(40)  # 原本 30 秒一輪的列表任務若還在，這段時間內會抓到

    assert post_row(db, later) is None


def test_crawler_restart_resumes_pending_tasks(api, fake_ptt, db, board):
    subprocess.run([*COMPOSE, "stop", "crawler"], check=True, capture_output=True)
    try:
        post_id = new_post(fake_ptt, board)
        api.post(f"/boards/{board}/crawl").raise_for_status()  # 爬蟲停止期間累積的任務
        time.sleep(5)
        assert post_row(db, post_id) is None
    finally:
        subprocess.run([*COMPOSE, "start", "crawler"], check=True, capture_output=True)

    wait_until(lambda: post_row(db, post_id), timeout_s=90)

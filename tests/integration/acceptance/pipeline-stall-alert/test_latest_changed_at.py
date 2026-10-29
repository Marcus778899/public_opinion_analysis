"""驗收 pipeline-stall-alert：真的 ClickHouse 讀到 posts_history 最新的 changed_at。"""

from datetime import UTC, datetime

import pytest

from radar.cdc.watchdog import read_latest_changed_at

pytestmark = pytest.mark.xdist_group("shared_radar_db")

COLS = (
    "post_id, board, push_count, boo_count, created_at, crawled_at, is_deleted, op, changed_at, lsn"
)


def _insert(ch, post_id: str, changed_at: str, lsn: int) -> None:
    ch.execute(
        f"INSERT INTO posts_history ({COLS}) VALUES "
        f"('{post_id}', 'Stock', 0, 0, '2026-10-01 00:00:00', '2026-10-01 00:00:00', 0, 'u', "
        f"'{changed_at}', {lsn})"
    )


@pytest.fixture
def ch(shared_clickhouse):
    shared_clickhouse.execute("TRUNCATE TABLE posts_history")
    return shared_clickhouse


def test_read_latest_changed_at_returns_max_over_all_rows(ch):
    _insert(ch, "Stock.M.1.A.001", "2026-10-29 01:00:00.000", 1)
    _insert(ch, "Stock.M.2.A.002", "2026-10-29 03:04:05.678", 2)
    _insert(ch, "Stock.M.3.A.003", "2026-10-28 23:59:59.999", 3)

    assert read_latest_changed_at(ch) == datetime(2026, 10, 29, 3, 4, 5, 678000, tzinfo=UTC)


def test_read_latest_changed_at_follows_new_rows(ch):
    _insert(ch, "Stock.M.1.A.001", "2026-10-29 01:00:00.000", 1)
    first = read_latest_changed_at(ch)
    _insert(ch, "Stock.M.1.A.001", "2026-10-29 02:00:00.000", 2)

    assert read_latest_changed_at(ch) > first


def test_read_latest_changed_at_empty_table_returns_none_or_epoch(ch):
    got = read_latest_changed_at(ch)
    assert got is None or got <= datetime(1970, 1, 2, tzinfo=UTC)

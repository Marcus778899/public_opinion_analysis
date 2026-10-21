"""PR #107 review 建議補的回歸：面板 6 爭議度留空與情緒套 min_score、面板 5 以 alert_id 去重。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.integration.dashboard._dash import (
    P_ALERTS,
    P_HOT,
    T_FROM,
    ch_post,
    insert_comments,
    insert_posts,
    load_dashboard,
    new_board,
    pid,
    predict,
    run_panel,
    sql_str,
    ts,
    votes,
)

pytestmark = pytest.mark.xdist_group("shared_radar_db")

AT = T_FROM + timedelta(hours=10)


@pytest.fixture(scope="module")
def dashboard() -> dict:
    return load_dashboard()


def _row(rows: list[dict], post_id: str) -> dict:
    found = [r for r in rows if post_id in str(r.get("標題"))]
    assert len(found) == 1, f"{post_id} 應剛好一列：{rows}"
    return found[0]


def _seed_hot(board: str, i: int, push: int, boo: int) -> str:
    p = pid(board, i)
    insert_posts([(p, board, AT)])
    insert_comments(votes(p, board, push, boo))
    return p


def test_hot_panel_leaves_controversy_empty_when_votes_below_ten(dashboard: dict) -> None:
    board = new_board()
    low = _seed_hot(board, 1, 6, 3)
    edge = _seed_hot(board, 2, 5, 5)
    rows = run_panel(dashboard, P_HOT, [board])
    assert _row(rows, low)["爭議度"] is None
    assert _row(rows, edge)["爭議度"] == 0.5


def test_hot_panel_shows_controversy_ratio_when_votes_at_least_ten(dashboard: dict) -> None:
    board = new_board()
    p = _seed_hot(board, 1, 8, 4)
    assert _row(run_panel(dashboard, P_HOT, [board]), p)["爭議度"] == 0.33


def test_hot_panel_sentiment_below_min_score_is_uncertain(dashboard: dict) -> None:
    board = new_board()
    p = _seed_hot(board, 1, 2, 1)
    predict(p, "negative", 0.4)
    assert _row(run_panel(dashboard, P_HOT, [board], "0.5"), p)["情緒"] == "不確定"


def test_hot_panel_sentiment_at_or_above_min_score_shows_polarity(dashboard: dict) -> None:
    board = new_board()
    p = _seed_hot(board, 1, 2, 1)
    predict(p, "negative", 0.4)
    assert _row(run_panel(dashboard, P_HOT, [board], "0.3"), p)["情緒"] == "負面"


def test_hot_panel_sentiment_is_blank_without_prediction(dashboard: dict) -> None:
    board = new_board()
    p = _seed_hot(board, 1, 2, 1)
    assert _row(run_panel(dashboard, P_HOT, [board]), p)["情緒"] == ""


def _insert_alert(alert_id: str, board: str, unit_key: str, created_at: datetime, value: float):
    ch_post(
        "INSERT INTO alerts (alert_id, unit_type, unit_key, board, window_start, window_end, "
        "value, baseline, zscore, sample_post_ids, created_at) VALUES "
        f"('{alert_id}', 'board', {sql_str(unit_key)}, {sql_str(board)}, '{ts(created_at)}', "
        f"'{ts(created_at)}', {value}, 2, 3.5, [], '{ts(created_at)}')"
    )


def test_alert_panel_dedupes_rows_with_same_alert_id(dashboard: dict) -> None:
    board = new_board()
    key = f"k{uuid.uuid4().hex}"
    alert_id = str(uuid.uuid4())
    now = datetime.now(UTC)
    _insert_alert(alert_id, board, key, now - timedelta(hours=1), 10)
    _insert_alert(alert_id, board, key, now - timedelta(hours=1), 10)
    rows = [r for r in run_panel(dashboard, P_ALERTS, []) if key in str(r.get("標題"))]
    assert len(rows) == 1


def test_alert_panel_keeps_distinct_alert_ids_and_ignores_older_than_24h(
    dashboard: dict,
) -> None:
    board = new_board()
    key = f"k{uuid.uuid4().hex}"
    old_key = f"k{uuid.uuid4().hex}"
    now = datetime.now(UTC)
    _insert_alert(str(uuid.uuid4()), board, key, now - timedelta(hours=1), 10)
    _insert_alert(str(uuid.uuid4()), board, key, now - timedelta(hours=2), 12)
    _insert_alert(str(uuid.uuid4()), board, old_key, now - timedelta(hours=25), 10)
    rows = run_panel(dashboard, P_ALERTS, [])
    assert len([r for r in rows if key in str(r.get("標題"))]) == 2
    assert not [r for r in rows if old_key in str(r.get("標題"))]

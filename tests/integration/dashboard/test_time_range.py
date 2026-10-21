"""$__timeFilter_ms 對 DateTime64(6) 的展開：時間範圍邊界內外各 2 秒（誤差 1 秒內可接受）。"""

from datetime import timedelta

import pytest

from tests.integration.dashboard._dash import (
    P_DISPUTED,
    P_DISTRIBUTION,
    P_VOLUME,
    T_FROM,
    T_TO,
    expand_vars,
    frames_numeric_sum,
    insert_comments,
    insert_posts,
    load_dashboard,
    new_board,
    panel_targets,
    pid,
    run_panel,
    votes,
)

pytestmark = pytest.mark.xdist_group("shared_radar_db")

EDGE = timedelta(seconds=2)


@pytest.fixture(scope="module")
def dashboard() -> dict:
    return load_dashboard()


def test_volume_panel_includes_comments_inside_and_excludes_outside_both_edges(
    dashboard: dict,
) -> None:
    board = new_board()
    p = pid(board)
    times = [T_FROM - EDGE, T_FROM + EDGE, T_TO - EDGE, T_TO + EDGE]
    insert_comments([(p, board, i + 1, "push", at) for i, at in enumerate(times)])
    target = panel_targets(dashboard, P_VOLUME)[0]
    total = frames_numeric_sum(target, expand_vars(target["rawSql"], [board]))
    assert total == 2


def test_distribution_panel_includes_posts_inside_and_excludes_outside_both_edges(
    dashboard: dict,
) -> None:
    board = new_board()
    times = [T_FROM - EDGE, T_FROM + EDGE, T_TO - EDGE, T_TO + EDGE]
    insert_posts([(pid(board, i + 1), board, at) for i, at in enumerate(times)])
    target = panel_targets(dashboard, P_DISTRIBUTION)[0]
    total = frames_numeric_sum(target, expand_vars(target["rawSql"], [board]))
    assert total == 2


def test_disputed_panel_includes_posts_inside_and_excludes_outside_both_edges(
    dashboard: dict,
) -> None:
    board = new_board()
    times = [T_FROM - EDGE, T_FROM + EDGE, T_TO - EDGE, T_TO + EDGE]
    insert_posts([(pid(board, i + 1), board, at) for i, at in enumerate(times)])
    for i in range(4):
        insert_comments(votes(pid(board, i + 1), board, 6, 6))
    rows = run_panel(dashboard, P_DISPUTED, [board])
    titles = " ".join(str(v) for r in rows for v in r.values())
    assert pid(board, 2) in titles and pid(board, 3) in titles
    assert pid(board, 1) not in titles and pid(board, 4) not in titles

"""board、min_score 變數：讀回、展開（All／單選／多選／空）、單引號與非數字。"""

import pytest

from tests.integration.dashboard._dash import (
    BOARD_PANELS,
    P_DISTRIBUTION,
    ds_query,
    load_dashboard,
    quote,
    run_panel,
    seed_board_with_comment,
    variable,
)

pytestmark = pytest.mark.xdist_group("shared_radar_db")


@pytest.fixture(scope="module")
def dashboard() -> dict:
    return load_dashboard()


def board_options(dashboard: dict) -> list[str]:
    var = variable(dashboard, "board")
    q = var["query"]
    sql = q["rawSql"] if isinstance(q, dict) else q
    target = {"format": 1, "queryType": "table", "editorType": "sql"}
    rows = ds_query(target, sql)
    return [str(next(iter(r.values()))) for r in rows]


def test_board_variable_query_lists_seeded_boards(dashboard: dict) -> None:
    a, b = seed_board_with_comment(), seed_board_with_comment()
    options = board_options(dashboard)
    assert a.board in options and b.board in options


def test_board_variable_is_multi_select_with_all(dashboard: dict) -> None:
    var = variable(dashboard, "board")
    assert var["multi"] is True and var["includeAll"] is True


def test_single_board_selection_returns_only_that_board(dashboard: dict) -> None:
    a, b = seed_board_with_comment(), seed_board_with_comment()
    rows = run_panel(dashboard, P_DISTRIBUTION, [a.board])
    text = " ".join(str(v) for r in rows for v in r.values())
    assert a.board in text and b.board not in text


def test_multi_board_selection_returns_all_selected_boards(dashboard: dict) -> None:
    a, b, c = (seed_board_with_comment() for _ in range(3))
    rows = run_panel(dashboard, P_DISTRIBUTION, [a.board, b.board])
    text = " ".join(str(v) for r in rows for v in r.values())
    assert a.board in text and b.board in text and c.board not in text


def test_all_selection_expands_every_option_without_error_for_every_panel(
    dashboard: dict,
) -> None:
    seeded = seed_board_with_comment()
    options = board_options(dashboard)
    assert seeded.board in options
    for title in BOARD_PANELS:
        run_panel(dashboard, title, options)
    rows = run_panel(dashboard, P_DISTRIBUTION, options)
    assert seeded.board in " ".join(str(v) for r in rows for v in r.values())


@pytest.mark.parametrize("title", BOARD_PANELS)
def test_empty_board_list_does_not_break_panel(dashboard: dict, title: str) -> None:
    # 沒有任何看板時變數展開為空字串，SQL 變成 board IN ()
    assert run_panel(dashboard, title, []) == []


def test_quote_helper_matches_clickhouse_escaping() -> None:
    assert quote("a'b\\") == "'a\\'b\\\\'"

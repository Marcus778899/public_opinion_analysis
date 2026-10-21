"""L-5 回歸：網址參數帶入含單引號或 SQL 片段的 board、min_score，不可改變查詢結構。

變數展開依 Grafana 前端的格式模擬（_dash.grafana_format）。報錯或回空都可以，
不可讓別的看板的資料出現，也不可讓 min_score 的結果和「非數字」時不同。
"""

import json

import pytest

from tests.integration.dashboard._dash import (
    ALL_PANELS,
    BOARD_PANELS,
    P_DISTRIBUTION,
    P_HOT,
    QueryError,
    Seeded,
    bare_references,
    insert_comments,
    load_dashboard,
    panel_targets,
    predict,
    run_panel,
    seed_board_with_comment,
    votes,
)

pytestmark = pytest.mark.xdist_group("shared_radar_db")

QUOTE_PAYLOADS = [
    "x') OR 1=1 OR ('",
    "') OR 1=1 --",
    "'",
    "0.5' OR '1'='1",
    "0.5'), ('",
    "x'; SELECT 1 --",
]
# Grafana 的 sqlstring 只把 ' 變成 ''，ClickHouse 卻把 \' 當跳脫的引號，所以反斜線要另外擋
BACKSLASH_PAYLOADS = ["\\') OR 1=1 --", "\\", "0.5\\", "\\' OR 1=1 OR board IN (\\'"]


@pytest.fixture(scope="module")
def dashboard() -> dict:
    return load_dashboard()


def seed_full() -> Seeded:
    """每個面板都查得到資料：有推文、情緒預測、至少 10 個推噓。"""
    seeded = seed_board_with_comment()
    predict(seeded.post_id, "negative", 0.9)
    insert_comments([c for c in votes(seeded.post_id, seeded.board, 6, 6) if c[2] > 1])
    return seeded


def _text(rows: list[dict]) -> str:
    return " ".join(str(v) for r in rows for v in r.values())


@pytest.mark.parametrize("title", ALL_PANELS)
def test_panel_sql_variables_all_use_an_escaping_format(dashboard: dict, title: str) -> None:
    for target in panel_targets(dashboard, title):
        sql = target["rawSql"]
        assert not bare_references(sql), f"沒指定跳脫格式就拼進 SQL：{bare_references(sql)}"
        for fmt in ("csv", "raw", "text", "glob", "pipe", "regex"):
            assert f":{fmt}}}" not in sql, f"{fmt} 格式不跳脫單引號"


def test_min_score_reference_is_not_wrapped_in_hand_written_quotes(dashboard: dict) -> None:
    # sqlstring 已經自帶引號；再包一層 '...' 會讓跳脫失效
    for title in (P_DISTRIBUTION, P_HOT):
        for target in panel_targets(dashboard, title):
            assert "'${min_score" not in target["rawSql"]
            assert "'$min_score" not in target["rawSql"]


@pytest.mark.parametrize("title", [P_DISTRIBUTION, P_HOT])
def test_min_score_threshold_still_applies_with_escaped_format(dashboard: dict, title: str) -> None:
    seeded = seed_board_with_comment()
    predict(seeded.post_id, "negative", 0.6)
    key, low, high = ("負面", 1, 0) if title == P_DISTRIBUTION else ("情緒", "負面", "不確定")
    assert run_panel(dashboard, title, [seeded.board], min_score="0.5")[0][key] == low
    rows = run_panel(dashboard, title, [seeded.board], min_score="0.7")
    assert rows[0][key] == high
    if title == P_DISTRIBUTION:
        assert rows[0]["不確定"] == 1


@pytest.mark.parametrize("payload", QUOTE_PAYLOADS)
@pytest.mark.parametrize("title", BOARD_PANELS)
def test_board_value_with_quote_does_not_change_query_structure(
    dashboard: dict, title: str, payload: str
) -> None:
    other = seed_full()
    # 對照組：正常值先成功，否則下面的「報錯」可能只是 plugin 全面失效
    assert run_panel(dashboard, title, [other.board])
    try:
        rows = run_panel(dashboard, title, [payload])
    except QueryError:
        return
    assert other.board not in _text(rows), "board 的單引號改變了查詢結構"


@pytest.mark.parametrize("payload", QUOTE_PAYLOADS)
@pytest.mark.parametrize("title", [P_DISTRIBUTION, P_HOT])
def test_min_score_value_with_quote_does_not_change_query_structure(
    dashboard: dict, title: str, payload: str
) -> None:
    mine = seed_board_with_comment()
    other = seed_board_with_comment()
    predict(mine.post_id, "negative", 0.9)
    baseline = run_panel(dashboard, title, [mine.board], min_score="abc")
    assert baseline
    try:
        rows = run_panel(dashboard, title, [mine.board], min_score=payload)
    except QueryError:
        return
    assert other.board not in _text(rows)
    assert rows == baseline, "min_score 的內容改變了查詢結果（非數字應與預設門檻相同）"


@pytest.mark.parametrize("payload", BACKSLASH_PAYLOADS)
@pytest.mark.parametrize("title", BOARD_PANELS)
def test_board_value_with_backslash_does_not_change_query_structure(
    dashboard: dict, title: str, payload: str
) -> None:
    other = seed_full()
    assert run_panel(dashboard, title, [other.board])
    try:
        rows = run_panel(dashboard, title, [payload])
    except QueryError:
        return
    assert other.board not in _text(rows), f"{json.dumps(payload)} 改變了查詢結構"


@pytest.mark.parametrize("payload", BACKSLASH_PAYLOADS)
@pytest.mark.parametrize("title", [P_DISTRIBUTION, P_HOT])
def test_min_score_value_with_backslash_does_not_change_query_structure(
    dashboard: dict, title: str, payload: str
) -> None:
    mine = seed_board_with_comment()
    other = seed_board_with_comment()
    predict(mine.post_id, "negative", 0.9)
    baseline = run_panel(dashboard, title, [mine.board], min_score="abc")
    try:
        rows = run_panel(dashboard, title, [mine.board], min_score=payload)
    except QueryError:
        return
    assert other.board not in _text(rows)
    assert rows == baseline

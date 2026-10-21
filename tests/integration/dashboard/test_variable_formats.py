"""L-5：使用者可經網址改的 $board、$min_score 不得進入 SQL 結構（開發規格 7.25）。

驗收用靜態檢查加正常值檢查，不送攻擊字串：每個引用都是 percentencode 且在 SQL 單引號內、
min_score 的選項是固定數字；再依格式的展開規則代入正常值，確認各面板結果正確。
"""

import re
import uuid
from datetime import timedelta

import pytest

from tests.integration.dashboard._dash import (
    ALL_PANELS,
    ALLOWED_FORMATS,
    BOARD_PANELS,
    FIXED_NUMBER,
    P_DISTRIBUTION,
    P_HOT,
    P_VOLUME,
    T_FROM,
    Seeded,
    insert_comments,
    insert_posts,
    load_dashboard,
    panel_targets,
    panel_text,
    pid,
    predict,
    references,
    run_panel,
    variable,
    votes,
)

pytestmark = pytest.mark.xdist_group("shared_radar_db")

THRESHOLDS = ["0.4", "0.5", "0.6", "0.7"]


@pytest.fixture(scope="module")
def dashboard() -> dict:
    return load_dashboard()


# ---------- 靜態檢查 ----------


@pytest.mark.parametrize("title", ALL_PANELS)
def test_every_board_and_min_score_reference_uses_percentencode(
    dashboard: dict, title: str
) -> None:
    for target in panel_targets(dashboard, title):
        refs = references(target["rawSql"])
        bad = [r.text for r in refs if r.fmt not in ALLOWED_FORMATS]
        assert not bad, f"只准 {sorted(ALLOWED_FORMATS)}，實際：{bad}"
        loose = [r.text for r in refs if not r.in_string]
        assert not loose, f"引用必須在 SQL 單引號內，實際不在：{loose}"


@pytest.mark.parametrize("title", BOARD_PANELS)
def test_board_panels_reference_board_variable(dashboard: dict, title: str) -> None:
    names = {r.name for t in panel_targets(dashboard, title) for r in references(t["rawSql"])}
    assert "board" in names


def test_min_score_options_are_all_fixed_numbers(dashboard: dict) -> None:
    var = variable(dashboard, "min_score")
    assert var["type"] == "custom"
    values = [str(o["value"]) for o in var["options"]]
    assert values == THRESHOLDS
    assert all(FIXED_NUMBER.fullmatch(v) for v in values + [str(var["current"]["value"])])
    assert all(FIXED_NUMBER.fullmatch(p) for p in re.split(r"\s*,\s*", str(var["query"]).strip()))


def test_references_helper_detects_quoted_and_formatted_references() -> None:
    sql = "a IN ('${board:sqlstring}') AND x > $min_score AND y = '${min_score:percentencode}'"
    got = [(r.name, r.fmt, r.in_string) for r in references(sql)]
    assert got == [
        ("board", "sqlstring", True),
        ("min_score", None, False),
        ("min_score", "percentencode", True),
    ]


# ---------- 正常值 ----------


def _seed(board: str) -> Seeded:
    """每個面板都查得到資料：有推文、情緒預測、至少 10 個推噓。"""
    post = pid(board)
    at = T_FROM + timedelta(hours=10)
    insert_posts([(post, board, at)])
    insert_comments([(post, board, 1, "push", at)])
    predict(post, "negative", 0.55)
    insert_comments([c for c in votes(post, board, 6, 6) if c[2] > 1])
    return Seeded(board, post)


@pytest.mark.parametrize("min_score", THRESHOLDS)
@pytest.mark.parametrize("title", [P_DISTRIBUTION, P_HOT])
def test_min_score_option_moves_post_between_category_and_unsure(
    dashboard: dict, title: str, min_score: str
) -> None:
    seeded = _seed(f"t{uuid.uuid4().hex}")
    sure = float(min_score) <= 0.55
    rows = run_panel(dashboard, title, [seeded.board], min_score=min_score)
    if title == P_DISTRIBUTION:
        assert (rows[0]["負面"], rows[0]["不確定"]) == ((1, 0) if sure else (0, 1))
    else:
        assert rows[0]["情緒"] == ("負面" if sure else "不確定")


@pytest.mark.parametrize("title", BOARD_PANELS)
def test_chinese_board_name_with_underscore_returns_its_own_rows_only(
    dashboard: dict, title: str
) -> None:
    mine = _seed(f"八卦_測試_{uuid.uuid4().hex}")
    other = _seed(f"八卦_測試x_{uuid.uuid4().hex}")  # 名稱相近，不可混入
    rows = run_panel(dashboard, title, [mine.board])
    assert rows
    text = panel_text(dashboard, title, [mine.board])
    if title == P_VOLUME:
        assert mine.board in text, "寬表的看板名稱在欄位 labels，應能讀到自己的看板"
    assert other.board not in text
    if title != P_VOLUME:
        assert run_panel(dashboard, title, [f"八卦_沒有資料_{uuid.uuid4().hex}"]) == []


def test_two_selected_boards_with_chinese_names_both_appear(dashboard: dict) -> None:
    a = _seed(f"股票_討論_{uuid.uuid4().hex}")
    b = _seed(f"c_{uuid.uuid4().hex}")
    rows = run_panel(dashboard, P_DISTRIBUTION, [a.board, b.board])
    assert {r["board"] for r in rows} == {a.board, b.board}

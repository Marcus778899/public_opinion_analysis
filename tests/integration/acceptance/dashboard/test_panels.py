"""驗收 dashboard-panels（開發規格 7.25「面板」表 1～6、變數、時間巨集、連結規則）。

讀 infra/grafana/dashboards/radar.json，把每個面板的 SQL 代換巨集與變數後，以唯讀帳號
在 radar DB 執行，結果符合種子資料。plugin 實際展開巨集的結果由 dashboard-integration 驗證。

種子資料放 radar DB（管理帳號寫入），看板名稱帶 uuid，變數 board 只代入自己的看板，
標 xdist_group("shared_radar_db") 避免被 cdc 模組 TRUNCATE 清掉（#111），
也不斷言整張表（開發規格 7.26）。測試帳密與 compose.yaml 一致。
面板的欄位名稱規格沒有訂，所以結果以「內容」辨認（標題、看板、類別名稱、數值），不靠欄名。
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tests.integration.dashboard._dash import (
    ALLOWED_FORMATS,
    FIXED_NUMBER,
    references,
)

pytestmark = pytest.mark.xdist_group("shared_radar_db")

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD = ROOT / "infra" / "grafana" / "dashboards" / "radar.json"
DATASOURCE_UID = "radar-clickhouse"
RO_USER = os.environ.get("CLICKHOUSE_GRAFANA_USER", "grafana")
RO_PASSWORD = os.environ.get("CLICKHOUSE_GRAFANA_PASSWORD", "it")
ADMIN_USER, ADMIN_PASSWORD = "radar", "it"
RADAR_DB = "radar"

P_VOLUME = "各看板推文量"
P_DISTRIBUTION = "情緒分布"
P_TREND = "情緒趨勢"
P_DISPUTED = "爭議度最高的文章"
P_ALERTS = "近 24 小時警示"
P_HOT = "熱門文章排行"
PANEL_TYPES = {
    P_VOLUME: {"timeseries"},
    P_DISTRIBUTION: {"barchart", "bargauge"},
    P_TREND: {"timeseries"},
    P_DISPUTED: {"table"},
    P_ALERTS: {"table"},
    P_HOT: {"table"},
}
TIME_PANELS = [P_VOLUME, P_DISTRIBUTION, P_TREND, P_DISPUTED, P_HOT]
BOARD_PANELS = [P_VOLUME, P_DISTRIBUTION, P_TREND, P_DISPUTED, P_HOT]
ALLOWED_TOKENS = {"__timeFilter_ms", "__timeInterval", "board", "min_score"}

LABEL_NEG, LABEL_NEU, LABEL_POS, LABEL_UNSURE, LABEL_NONE = "負面", "中立", "正面", "不確定", "尚無"
LABELS = {LABEL_NEG, LABEL_NEU, LABEL_POS, LABEL_UNSURE, LABEL_NONE}
POLARITY_LABEL = {"negative": LABEL_NEG, "neutral": LABEL_NEU, "positive": LABEL_POS}

# 時間範圍：2026-02-09 ～ 02-12（UTC）；種子資料與邊界都以它為準
T_FROM = datetime(2026, 2, 9, tzinfo=UTC)
T_TO = datetime(2026, 2, 12, tzinfo=UTC)
GOOD_URL = "https://www.ptt.cc/bbs/Stock/M.1.A.000.html"


# ---------- ClickHouse 存取 ----------


def _post(sql: str, user: str, password: str) -> tuple[int, str]:
    base = os.environ["IT_CLICKHOUSE_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/?database={RADAR_DB}",
        data=sql.encode(),
        method="POST",
        headers={"X-ClickHouse-User": user, "X-ClickHouse-Key": password},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode().strip()


def _admin(sql: str) -> None:
    status, body = _post(sql, ADMIN_USER, ADMIN_PASSWORD)
    assert status == 200, body


def _ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


# ---------- dashboard JSON 與 SQL 代換 ----------


@pytest.fixture(scope="module")
def dashboard() -> dict:
    if not DASHBOARD.exists():
        pytest.fail(f"{DASHBOARD.relative_to(ROOT)} 不存在", pytrace=False)
    return json.loads(DASHBOARD.read_text(encoding="utf-8"))


def _flatten(panels: list[dict]) -> list[dict]:
    out: list[dict] = []
    for p in panels:
        out.append(p)
        out.extend(_flatten(p.get("panels", [])))
    return out


def _panel(dashboard: dict, title: str) -> dict:
    found = [p for p in _flatten(dashboard.get("panels", [])) if p.get("title") == title]
    assert len(found) == 1, f"面板「{title}」應剛好一個，實際 {len(found)}"
    return found[0]


def _sqls(panel: dict) -> list[str]:
    sqls = [t.get("rawSql") or t.get("query") for t in panel.get("targets", [])]
    sqls = [s for s in sqls if isinstance(s, str) and s.strip()]
    assert sqls, f"面板「{panel.get('title')}」沒有 SQL（targets[].rawSql）"
    return sqls


def _tokens(sql: str) -> set[str]:
    return set(re.findall(r"\$\{?(\w+)", sql))


_VAR = re.compile(
    r"\$\{(?P<a>board|min_score)(?::(?P<fa>\w+))?\}"
    r"|\$(?P<b>board|min_score)\b"
    r"|\[\[(?P<c>board|min_score)(?::(?P<fc>\w+))?\]\]"
)


def _expand(sql: str, boards: list[str], min_score: str, interval_s: int = 3600) -> str:
    """依 Grafana／ClickHouse plugin 的展開方式代換；多選變數預設為 'a','b'。"""
    sql = re.sub(
        r"\$__timeFilter_ms\(\s*([^)]+?)\s*\)",
        lambda m: (
            f"{m[1]} >= fromUnixTimestamp64Milli({_ms(T_FROM)}) "
            f"AND {m[1]} <= fromUnixTimestamp64Milli({_ms(T_TO)})"
        ),
        sql,
    )
    sql = re.sub(
        r"\$__timeInterval\(\s*([^)]+?)\s*\)",
        lambda m: f"toStartOfInterval(toDateTime({m[1]}), INTERVAL {interval_s} second)",
        sql,
    )

    def var(m: re.Match) -> str:
        name = m["a"] or m["b"] or m["c"]
        fmt = m["fa"] or m["fc"]
        values = boards if name == "board" else [min_score]
        if fmt == "percentencode":  # Grafana：多選先包成 {a,b} 再編碼，!'()* 也編碼
            joined = "{" + ",".join(values) + "}" if name == "board" else values[0]
            return urllib.parse.quote(joined, safe="")
        if fmt == "csv" or (fmt is None and name == "min_score"):
            return ",".join(values)
        if fmt == "sqlstring":  # Grafana：' 變成 ''
            return ",".join("'" + v.replace("'", "''") + "'" for v in values)
        if fmt == "singlequote":  # Grafana：' 變成 \\'
            return ",".join("'" + v.replace("'", "\\'") + "'" for v in values)
        if fmt is None:
            return ",".join(f"'{v}'" for v in values)
        pytest.fail(f"測試不支援的變數格式 :{fmt}", pytrace=False)

    sql = _VAR.sub(var, sql)
    assert "$" not in sql, f"仍有未展開的巨集或變數：{sql}"
    return sql.strip().rstrip(";")


def _run(
    dashboard: dict,
    title: str,
    boards: list[str],
    min_score: str = "0.5",
    interval_s: int = 3600,
) -> list[dict]:
    rows: list[dict] = []
    for sql in _sqls(_panel(dashboard, title)):
        expanded = _expand(sql, boards, min_score, interval_s)
        status, body = _post(f"{expanded}\nFORMAT JSONEachRow", RO_USER, RO_PASSWORD)
        assert status == 200, f"面板「{title}」以唯讀帳號執行失敗：{body}\n{expanded}"
        rows += [json.loads(line) for line in body.splitlines() if line]
    return rows


# ---------- 結果的辨認（不依賴欄名） ----------


def _num(v: object) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v):
        return float(v)
    return None


def _nums(row: dict) -> list[float]:
    return [n for v in row.values() if (n := _num(v)) is not None]


def _has_num(row: dict, x: float) -> bool:
    return any(abs(n - x) < 1e-6 for n in _nums(row))


def _distribution(rows: list[dict]) -> dict[str, float]:
    """長表（類別一欄、n 一欄）或寬表（類別當欄名）都歸成 類別 -> n。"""
    out = dict.fromkeys(LABELS, 0.0)
    for row in rows:
        for k, v in row.items():
            if k in LABELS and (n := _num(v)) is not None:
                out[k] += n
        labels = [v for v in row.values() if isinstance(v, str) and v in LABELS]
        if labels and _nums(row):
            out[labels[0]] += _nums(row)[-1]
    return out


def _by_bucket(rows: list[dict]) -> dict[tuple, dict[str, float]]:
    """依時間（非數字、非類別的儲存格）分組，每組為 類別 -> 值。"""
    out: dict[tuple, dict[str, float]] = {}
    for row in rows:
        key = tuple(
            str(v)
            for v in row.values()
            if _num(v) is None and not (isinstance(v, str) and v in LABELS)
        )
        bucket = out.setdefault(key, dict.fromkeys(LABELS, 0.0))
        for label, n in _distribution([row]).items():
            bucket[label] += n
    return out


def _order(rows: list[dict], post_ids: list[str]) -> list[str]:
    """依結果列的順序，回傳標題含 T[<post_id>] 的文章。"""
    found: list[str] = []
    for row in rows:
        for pid in post_ids:
            if any(isinstance(v, str) and _title(pid) in v for v in row.values()):
                found.append(pid)
                break
    return found


def _row_of(rows: list[dict], pid: str) -> dict:
    for row in rows:
        if any(isinstance(v, str) and _title(pid) in v for v in row.values()):
            return row
    pytest.fail(f"結果裡找不到 {pid}：{rows}", pytrace=False)


# ---------- 種子資料 ----------


def _board() -> str:
    return f"t{uuid.uuid4().hex}"


def _pid(board: str, i: int = 0) -> str:
    return f"{board}.M.1.A.{i:03d}"


def _title(pid: str) -> str:
    return f"T[{pid}]"


def _insert_posts(rows: list[tuple[str, str, datetime, str, int]]) -> None:
    """rows: (post_id, board, created_at, url, lsn)；標題固定為 _title(post_id)。"""
    values = ", ".join(
        f"('{pid}', '{board}', '{_title(pid)}', '{url}', 0, 0, '{_ts(at)}', '{_ts(at)}', 0, {lsn})"
        for pid, board, at, url, lsn in rows
    )
    _admin(
        "INSERT INTO posts_latest (post_id, board, title, url, push_count, boo_count, "
        f"created_at, crawled_at, is_deleted, lsn) VALUES {values}"
    )


def _post_in(board: str, i: int, at: datetime, url: str = GOOD_URL, lsn: int = 1) -> tuple:
    return (_pid(board, i), board, at, url, lsn)


# (post_id, board, floor, type, commented_at, lsn, is_deleted)
type CommentRow = tuple[str, str, int, str, datetime, int, int]


def _insert_comments(rows: list[CommentRow]) -> None:
    values = ", ".join(
        f"('{pid}', '{board}', {floor}, '{ctype}', 'u', 'x', '{_ts(at)}', "
        f"'2026-01-01 00:00:00.000', {lsn}, {deleted})"
        for pid, board, floor, ctype, at, lsn, deleted in rows
    )
    _admin(
        "INSERT INTO comments_latest (post_id, board, floor, type, user_id, content, "
        f"commented_at, changed_at, lsn, is_deleted) VALUES {values}"
    )


def _votes(pid: str, board: str, push: int, boo: int, arrow: int = 0) -> list[CommentRow]:
    at = T_FROM + timedelta(hours=10)
    kinds = ["push"] * push + ["boo"] * boo + ["arrow"] * arrow
    return [(pid, board, i + 1, k, at, 1, 0) for i, k in enumerate(kinds)]


def _predict(pid: str, polarity: str, score: float, at: str = "2026-02-01 00:00:00.000000") -> None:
    others = {"negative", "neutral", "positive"} - {polarity}
    rest = (1 - score) / 2
    scores = {polarity: score, **dict.fromkeys(sorted(others), rest)}
    mapping = "{" + ", ".join(f"'{k}': {v}" for k, v in scores.items()) + "}"
    _admin(
        "INSERT INTO predictions (post_id, model_version, predicted_at, polarity, scores) "
        f"VALUES ('{pid}', 'v1', '{at}', '{polarity}', {mapping})"
    )


# ========== 面板定義（靜態） ==========


def test_dashboard_has_the_six_documented_panels(dashboard: dict) -> None:
    titles = [p.get("title") for p in _flatten(dashboard.get("panels", []))]
    for title in PANEL_TYPES:
        assert titles.count(title) == 1, f"面板「{title}」應剛好一個：{titles}"


@pytest.mark.parametrize("title", list(PANEL_TYPES))
def test_panel_uses_documented_visualization_type(dashboard: dict, title: str) -> None:
    assert _panel(dashboard, title)["type"] in PANEL_TYPES[title]


@pytest.mark.parametrize("title", list(PANEL_TYPES))
def test_panel_queries_the_provisioned_clickhouse_datasource(dashboard: dict, title: str) -> None:
    panel = _panel(dashboard, title)
    for target in panel["targets"]:
        ds = target.get("datasource") or panel.get("datasource") or {}
        assert ds.get("uid") == DATASOURCE_UID


@pytest.mark.parametrize("title", list(PANEL_TYPES))
def test_panel_sql_has_no_settings_clause(dashboard: dict, title: str) -> None:
    # 唯讀帳號 readonly=1，SETTINGS 會被拒絕
    for sql in _sqls(_panel(dashboard, title)):
        assert not re.search(r"\bSETTINGS\b", sql, re.I)


@pytest.mark.parametrize("title", list(PANEL_TYPES))
def test_panel_sql_uses_only_documented_macros_and_variables(dashboard: dict, title: str) -> None:
    for sql in _sqls(_panel(dashboard, title)):
        assert _tokens(sql) <= ALLOWED_TOKENS, _tokens(sql) - ALLOWED_TOKENS
        assert not re.search(r"\$__timeFilter\(", sql)


@pytest.mark.parametrize("title", TIME_PANELS)
def test_panel_follows_dashboard_time_range(dashboard: dict, title: str) -> None:
    assert any("$__timeFilter_ms(" in sql for sql in _sqls(_panel(dashboard, title)))


def test_alert_panel_does_not_follow_time_range(dashboard: dict) -> None:
    for sql in _sqls(_panel(dashboard, P_ALERTS)):
        assert "$__timeFilter" not in sql


def test_volume_panel_buckets_with_time_interval_macro(dashboard: dict) -> None:
    assert any("$__timeInterval(" in s for s in _sqls(_panel(dashboard, P_VOLUME)))


@pytest.mark.parametrize("title", BOARD_PANELS)
def test_panel_filters_by_board_variable(dashboard: dict, title: str) -> None:
    assert any("board" in _tokens(sql) for sql in _sqls(_panel(dashboard, title)))


def test_distribution_panel_uses_min_score_variable(dashboard: dict) -> None:
    assert any("min_score" in _tokens(s) for s in _sqls(_panel(dashboard, P_DISTRIBUTION)))


def _variable(dashboard: dict, name: str) -> dict:
    found = [v for v in dashboard.get("templating", {}).get("list", []) if v.get("name") == name]
    assert len(found) == 1, f"變數 {name} 應剛好一個"
    return found[0]


def test_board_variable_is_multi_select_from_posts_latest(dashboard: dict) -> None:
    var = _variable(dashboard, "board")
    text = re.sub(r"\s+", " ", json.dumps(var, ensure_ascii=False)).lower()
    assert var.get("multi") is True
    assert "select distinct board from posts_latest" in text
    assert "settings" not in text


def test_min_score_variable_is_dropdown_with_four_options_defaulting_to_half(
    dashboard: dict,
) -> None:
    var = _variable(dashboard, "min_score")
    assert var["type"] == "custom"
    values = [str(o["value"]) for o in var["options"]]
    assert values == ["0.4", "0.5", "0.6", "0.7"]
    assert str(var.get("current", {}).get("value")) == "0.5"
    assert [str(o["value"]) for o in var["options"] if o.get("selected")] in ([], ["0.5"])
    assert str(var.get("query")).replace(" ", "") == "0.4,0.5,0.6,0.7"
    assert var.get("multi") in (None, False) and not var.get("includeAll")
    assert str(var.get("description", "")).strip(), "min_score 要有說明文字"


@pytest.mark.parametrize("title", list(PANEL_TYPES))
def test_every_board_and_min_score_reference_uses_percentencode(
    dashboard: dict, title: str
) -> None:
    for sql in _sqls(_panel(dashboard, title)):
        bad = [r.text for r in references(sql) if r.fmt not in ALLOWED_FORMATS]
        assert not bad, f"面板「{title}」只准 {sorted(ALLOWED_FORMATS)}，實際：{bad}"
        loose = [r.text for r in references(sql) if not r.in_string]
        assert not loose, f"面板「{title}」引用必須在 SQL 單引號內，實際不在：{loose}"


def test_min_score_options_and_default_are_fixed_numbers(dashboard: dict) -> None:
    var = _variable(dashboard, "min_score")
    values = [str(o["value"]) for o in var["options"]] + [str(var["current"]["value"])]
    assert all(FIXED_NUMBER.fullmatch(v) for v in values)
    assert all(FIXED_NUMBER.fullmatch(p.strip()) for p in str(var["query"]).split(","))


@pytest.mark.parametrize("min_score", ["0.4", "0.5", "0.6", "0.7"])
def test_every_min_score_option_gives_the_seeded_distribution(
    dashboard: dict, min_score: str
) -> None:
    board = _board()
    _insert_posts([_post_in(board, 1, T_FROM + timedelta(hours=1))])
    _predict(_pid(board, 1), "negative", 0.65)
    dist = _distribution(_run(dashboard, P_DISTRIBUTION, [board], min_score))
    unsure = float(min_score) > 0.65
    assert (dist[LABEL_NEG], dist[LABEL_UNSURE]) == ((0, 1) if unsure else (1, 0))


def test_chinese_board_name_with_underscore_is_matched_exactly(dashboard: dict) -> None:
    mine = f"八卦_測試_{uuid.uuid4().hex}"
    near = f"八卦_測試x_{uuid.uuid4().hex}"
    at = T_FROM + timedelta(hours=1)
    _insert_posts([_post_in(mine, 1, at), _post_in(near, 1, at)])
    _predict(_pid(mine, 1), "positive", 0.9)
    _predict(_pid(near, 1), "negative", 0.9)
    dist = _distribution(_run(dashboard, P_DISTRIBUTION, [mine]))
    assert (dist[LABEL_POS], dist[LABEL_NEG]) == (1, 0)
    dist_both = _distribution(_run(dashboard, P_DISTRIBUTION, [mine, near]))
    assert (dist_both[LABEL_POS], dist_both[LABEL_NEG]) == (1, 1)


def test_dashboard_json_contains_no_javascript_links(dashboard: dict) -> None:
    assert "javascript:" not in json.dumps(dashboard).lower()


@pytest.mark.parametrize("title", list(PANEL_TYPES))
def test_panel_sql_runs_with_readonly_user(dashboard: dict, title: str) -> None:
    _run(dashboard, title, [_board()])


@pytest.mark.parametrize("title", BOARD_PANELS)
def test_panel_returns_nothing_for_board_without_data(dashboard: dict, title: str) -> None:
    mine, other = _board(), _board()
    at = T_FROM + timedelta(hours=10)
    _insert_posts([_post_in(mine, 1, at)])
    _insert_comments(_votes(_pid(mine, 1), mine, 10, 10))
    _predict(_pid(mine, 1), "negative", 0.9)
    assert _run(dashboard, title, [other]) == []


# ========== 1 各看板推文量 ==========


def test_volume_counts_comments_per_interval_inside_time_range(dashboard: dict) -> None:
    board, other = _board(), _board()
    pid = _pid(board, 1)

    def c(floor: int, at: datetime, kind: str = "push", lsn: int = 1, deleted: int = 0) -> tuple:
        return (pid, board, floor, kind, at, lsn, deleted)

    h1 = datetime(2026, 2, 10, 1, 30, tzinfo=UTC)
    h3 = datetime(2026, 2, 10, 3, 10, tzinfo=UTC)
    _insert_comments(
        [
            c(1, T_FROM + timedelta(seconds=2)),  # 範圍起點內 2 秒
            c(2, h1, "push"),
            c(3, h1 + timedelta(minutes=5), "boo"),
            c(4, h1 + timedelta(minutes=10), "arrow"),
            c(5, h3),
            c(6, T_TO - timedelta(seconds=2)),  # 範圍終點內 2 秒
            c(7, T_FROM - timedelta(seconds=2)),  # 範圍外 2 秒
            c(8, T_TO + timedelta(seconds=2)),
            c(9, h1, "push", lsn=1),
            c(9, h1, "push", lsn=2, deleted=1),  # 已刪除，不計
            (_pid(other, 1), other, 1, "push", h1, 1, 0),  # 別的看板
        ]
    )
    rows = _run(dashboard, P_VOLUME, [board])
    counts = sorted(_nums(r)[-1] for r in rows)
    assert counts == [1, 1, 1, 3]


def test_volume_with_two_boards_selected_counts_both(dashboard: dict) -> None:
    a, b = _board(), _board()
    at = T_FROM + timedelta(hours=5)
    _insert_comments([(_pid(a, 1), a, 1, "push", at, 1, 0), (_pid(b, 1), b, 1, "push", at, 1, 0)])
    rows = _run(dashboard, P_VOLUME, [a, b])
    assert sum(_nums(r)[-1] for r in rows) == 2
    assert any(a in map(str, r.values()) or a in r for r in rows)
    assert any(b in map(str, r.values()) or b in r for r in rows)


# ========== 2 情緒分布 ==========


def _seed_distribution() -> str:
    board = _board()
    inside = T_FROM + timedelta(hours=10)
    posts = [
        _post_in(board, 1, inside),  # 負面 0.8
        _post_in(board, 2, inside),  # 先正面、後負面 -> 取最新（負面 0.8）
        _post_in(board, 3, inside),  # 中立 0.7
        _post_in(board, 4, inside),  # 正面 0.9
        _post_in(board, 5, inside),  # 正面 0.5（等於 min_score，不算不確定）
        _post_in(board, 6, inside),  # 負面 0.4（低於 min_score）
        _post_in(board, 7, inside),  # 尚無
        _post_in(board, 8, inside),  # 尚無
        _post_in(board, 9, T_FROM - timedelta(seconds=2)),  # 範圍外
        _post_in(board, 10, T_TO + timedelta(seconds=2)),  # 範圍外
        _post_in(board, 1, inside, lsn=2),  # 同一篇的新版本，不可重複計算
    ]
    _insert_posts(posts)
    _predict(_pid(board, 1), "negative", 0.8)
    _predict(_pid(board, 2), "positive", 0.9, "2026-02-01 00:00:00.000000")
    _predict(_pid(board, 2), "negative", 0.8, "2026-02-02 00:00:00.000000")
    _predict(_pid(board, 3), "neutral", 0.7)
    _predict(_pid(board, 4), "positive", 0.9)
    _predict(_pid(board, 5), "positive", 0.5)
    _predict(_pid(board, 6), "negative", 0.4)
    _predict(_pid(board, 9), "negative", 0.9)
    _predict(_pid(board, 10), "negative", 0.9)
    return board


def test_distribution_counts_each_category_inside_time_range(dashboard: dict) -> None:
    board = _seed_distribution()
    dist = _distribution(_run(dashboard, P_DISTRIBUTION, [board], "0.5"))
    assert dist == {
        LABEL_NEG: 2,
        LABEL_NEU: 1,
        LABEL_POS: 2,
        LABEL_UNSURE: 1,
        LABEL_NONE: 2,
    }


def test_distribution_raising_min_score_moves_posts_to_unsure(dashboard: dict) -> None:
    board = _seed_distribution()
    dist = _distribution(_run(dashboard, P_DISTRIBUTION, [board], "0.75"))
    assert dist == {
        LABEL_NEG: 2,
        LABEL_NEU: 0,
        LABEL_POS: 1,
        LABEL_UNSURE: 3,
        LABEL_NONE: 2,
    }


def test_distribution_post_without_prediction_is_none_not_unsure(dashboard: dict) -> None:
    board = _board()
    _insert_posts([_post_in(board, 1, T_FROM + timedelta(hours=1))])
    dist = _distribution(_run(dashboard, P_DISTRIBUTION, [board], "0.99"))
    assert dist[LABEL_NONE] == 1
    assert dist[LABEL_UNSURE] == 0


# ========== 3 情緒趨勢 ==========


def test_trend_groups_by_taipei_day_and_ignores_posts_without_prediction(
    dashboard: dict,
) -> None:
    board = _board()
    # 同一個 UTC 日：15:00 UTC = 台北 23:00（當天），17:00 UTC = 台北 01:00（隔天）
    day1 = datetime(2026, 2, 10, 15, 0, tzinfo=UTC)
    day2 = datetime(2026, 2, 10, 17, 0, tzinfo=UTC)
    before = T_FROM - timedelta(seconds=2)
    posts = [_post_in(board, i, day1) for i in range(1, 7)]
    posts += [_post_in(board, 7, day2), _post_in(board, 8, before)]
    _insert_posts(posts)
    for i in (1, 2, 3):
        _predict(_pid(board, i), "negative", 0.8)
    _predict(_pid(board, 4), "positive", 0.9)  # 5、6 沒有推論
    _predict(_pid(board, 7), "neutral", 0.8)
    _predict(_pid(board, 8), "negative", 0.8)  # 範圍外

    buckets = _by_bucket(_run(dashboard, P_TREND, [board]))
    assert len(buckets) == 2, buckets
    first, second = sorted(buckets.items())
    d1, d2 = first[1], second[1]
    assert d1[LABEL_NEG] > 0
    assert d1[LABEL_NEG] == pytest.approx(3 * d1[LABEL_POS])
    assert d1[LABEL_NEU] == 0
    assert d2[LABEL_NEU] > 0
    assert d2[LABEL_NEG] == d2[LABEL_POS] == 0
    for d in (d1, d2):
        assert d[LABEL_NONE] == 0


# ========== 4 爭議度最高的文章 ==========


def test_disputed_threshold_ordering_and_excluded_posts(dashboard: dict) -> None:
    board = _board()
    at = T_FROM + timedelta(hours=10)
    a, c, d, b, e, f, g, out = (_pid(board, i) for i in range(1, 9))
    _insert_posts([_post_in(board, i, at) for i in range(1, 8)])
    _insert_posts([_post_in(board, 8, T_FROM - timedelta(seconds=2))])
    rows = (
        _votes(a, board, 5, 5)  # 10 -> 納入，0.5
        + _votes(c, board, 2, 18)  # 20 -> 納入，0.9
        + _votes(d, board, 10, 0)  # 10 -> 納入，0
        + _votes(b, board, 1, 8)  # 9 -> 不納入
        + _votes(e, board, 5, 4, arrow=3)  # 推＋噓 = 9（箭頭不算）-> 不納入
        + _votes(f, board, 5, 4)
        + _votes(out, board, 1, 19)  # 範圍外
    )
    rows.append((f, board, 99, "boo", at, 1, 0))
    rows.append((f, board, 99, "boo", at, 2, 1))  # 第 5 個噓已刪除，仍是 9 -> 不納入
    _insert_comments(rows)
    result = _run(dashboard, P_DISPUTED, [board])
    assert _order(result, [a, b, c, d, e, f, g, out]) == [c, a, d]


def test_disputed_shows_at_most_twenty_ordered_by_boo_ratio(dashboard: dict) -> None:
    board = _board()
    at = T_FROM + timedelta(hours=10)
    pids = [_pid(board, i) for i in range(1, 23)]
    _insert_posts([_post_in(board, i, at) for i in range(1, 23)])
    rows: list[CommentRow] = []
    for i, pid in enumerate(pids, start=1):
        rows += _votes(pid, board, 10, i)  # 噓比例隨 i 增加
    _insert_comments(rows)
    result = _run(dashboard, P_DISPUTED, [board])
    assert _order(result, pids) == list(reversed(pids[2:]))


# ========== 5 近 24 小時警示 ==========


def _alert(board: str, unit_type: str, key: str, value: float, base: float, z: float, hours: int):
    _admin(
        "INSERT INTO alerts (alert_id, unit_type, unit_key, board, window_start, window_end, "
        "value, baseline, zscore, sample_post_ids, created_at) SELECT generateUUIDv4(), "
        f"'{unit_type}', '{key}', '{board}', now64(6) - INTERVAL {hours} HOUR, "
        f"now64(6) - INTERVAL {hours} HOUR, {value}, {base}, {z}, [], "
        f"now64(6) - INTERVAL {hours} HOUR"
    )


def test_alerts_show_last_24_hours_with_multiple_and_zscore(dashboard: dict) -> None:
    board = _board()
    pid = _pid(board, 1)
    _insert_posts([_post_in(board, 1, T_FROM)])
    _alert(board, "post", pid, 20, 4, 3.5, 1)  # 倍數 5
    _alert(board, "board", board, 6, 0.5, 4.5, 2)  # baseline < 1 以 1 計 -> 6
    _alert(board, "board", board, 3, 0, 5.5, 3)  # baseline 0 以 1 計 -> 3
    _alert(board, "board", board, 12, 3, 6.5, 23)  # 24 小時內 -> 4
    _alert(board, "board", board, 50, 1, 9.9, 25)  # 超過 24 小時 -> 不納入

    rows = [r for r in _run(dashboard, P_ALERTS, [board]) if board in map(str, r.values())]
    for z, multiple, value in ((3.5, 5.0, 20), (4.5, 6.0, 6), (5.5, 3.0, 3), (6.5, 4.0, 12)):
        (row,) = [r for r in rows if _has_num(r, z)]
        assert _has_num(row, multiple), row
        assert _has_num(row, value), row
    assert len(rows) == 4
    assert not any(_has_num(r, 9.9) for r in rows)


def test_alerts_post_alert_shows_post_title(dashboard: dict) -> None:
    board = _board()
    pid = _pid(board, 1)
    _insert_posts([_post_in(board, 1, T_FROM)])
    _alert(board, "post", pid, 20, 4, 3.5, 1)
    rows = [r for r in _run(dashboard, P_ALERTS, [board]) if board in map(str, r.values())]
    assert len(rows) == 1
    assert any(isinstance(v, str) and _title(pid) in v for v in rows[0].values())


# ========== 6 熱門文章排行 ==========


def test_hot_ranks_by_new_comments_in_range_with_votes_and_sentiment(dashboard: dict) -> None:
    board = _board()
    x, y, z, w = (_pid(board, i) for i in range(1, 5))
    old = T_FROM - timedelta(days=3)  # 文章比時間範圍早發；推文在範圍內仍要計
    _insert_posts([_post_in(board, i, old) for i in range(1, 5)])
    inside = T_FROM + timedelta(hours=10)
    rows = _votes(x, board, 4, 1)
    rows += [(y, board, i, "push", inside, 1, 0) for i in (1, 2, 3)]
    rows += [(y, board, 10, "push", T_FROM - timedelta(seconds=2), 1, 0)]
    rows += [(y, board, 11, "push", T_TO + timedelta(seconds=2), 1, 0)]
    rows += [(z, board, i, "push", T_FROM - timedelta(days=1), 1, 0) for i in range(1, 8)]
    rows += [(w, board, 1, "push", inside, 1, 0), (w, board, 1, "push", inside, 2, 1)]
    _insert_comments(rows)
    _predict(x, "positive", 0.9)

    result = _run(dashboard, P_HOT, [board])
    assert _order(result, [x, y, z, w]) == [x, y]
    row_x, row_y = _row_of(result, x), _row_of(result, y)
    assert _has_num(row_x, 5) and _has_num(row_x, 4) and _has_num(row_x, 1)
    assert _has_num(row_y, 3)
    assert any(v in ("positive", LABEL_POS) for v in row_x.values())
    assert not any(
        v in ("positive", "negative", "neutral", *LABELS)
        for v in row_y.values()
        if isinstance(v, str)
    )


def test_hot_shows_at_most_twenty_most_commented(dashboard: dict) -> None:
    board = _board()
    pids = [_pid(board, i) for i in range(1, 23)]
    _insert_posts([_post_in(board, i, T_FROM) for i in range(1, 23)])
    inside = T_FROM + timedelta(hours=10)
    rows: list[CommentRow] = []
    for i, pid in enumerate(pids, start=1):
        rows += [(pid, board, n, "push", inside, 1, 0) for n in range(1, i + 1)]
    _insert_comments(rows)
    result = _run(dashboard, P_HOT, [board])
    assert _order(result, pids) == list(reversed(pids[2:]))


# ========== 標題連結：只用 posts_latest.url，限 https://www.ptt.cc/ ==========

BAD_URLS = [
    "javascript:alert(1)",
    "http://www.ptt.cc/bbs/Stock/M.1.A.001.html",
    "https://www.ptt.cc.evil.example/bbs/Stock/M.1.A.001.html",
    "https://evil.example/https://www.ptt.cc/",
    "data:text/html,<script>alert(1)</script>",
]


def _seed_links(kind: str) -> tuple[str, list[str], list[str]]:
    board = _board()
    at = T_FROM + timedelta(hours=10)
    urls = [GOOD_URL, *BAD_URLS]
    pids = [_pid(board, i) for i in range(1, len(urls) + 1)]
    _insert_posts([_post_in(board, i, at, url) for i, url in enumerate(urls, start=1)])
    rows: list[CommentRow] = []
    for pid in pids:
        if kind == "disputed":
            rows += _votes(pid, board, 5, 5)
        else:
            rows += [(pid, board, n, "push", at, 1, 0) for n in range(1, 4)]
    _insert_comments(rows)
    return board, pids, urls


@pytest.mark.parametrize(("title", "kind"), [(P_DISPUTED, "disputed"), (P_HOT, "hot")])
def test_table_title_links_only_ptt_https_urls(dashboard: dict, title: str, kind: str) -> None:
    board, pids, urls = _seed_links(kind)
    result = _run(dashboard, title, [board])
    assert sorted(_order(result, pids)) == sorted(pids)  # 文章仍列出，只是沒有連結
    good = _row_of(result, pids[0])
    assert GOOD_URL in good.values()
    for pid, url in zip(pids[1:], urls[1:], strict=True):
        row = _row_of(result, pid)
        assert not any(isinstance(v, str) and url in v for v in row.values()), (url, row)

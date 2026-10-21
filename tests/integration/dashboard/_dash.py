"""dashboard 整合測試共用：Grafana API、種子資料、前端變數展開的模擬（開發規格 7.25）。

/api/ds/query 的後端只展開 $__timeFilter_ms、$__timeInterval；$board、$min_score 是 Grafana
前端代換的，所以這裡依所選格式的展開規則代換後再送 API。
測試帳密與 compose.yaml 一致，不讀 .env。種子資料寫 radar DB，看板名稱帶 uuid。
"""

import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

DS = {"type": "grafana-clickhouse-datasource", "uid": "radar-clickhouse"}
DASHBOARD_UID = "radar"
GRAFANA_AUTH = ("admin", os.environ.get("GRAFANA_ADMIN_PASSWORD", "it"))
ADMIN_USER, ADMIN_PASSWORD = "radar", "it"
RADAR_DB = "radar"

P_VOLUME = "各看板推文量"
P_DISTRIBUTION = "情緒分布"
P_TREND = "情緒趨勢"
P_DISPUTED = "爭議度最高的文章"
P_ALERTS = "近 24 小時警示"
P_HOT = "熱門文章排行"
ALL_PANELS = [P_VOLUME, P_DISTRIBUTION, P_TREND, P_DISPUTED, P_ALERTS, P_HOT]
BOARD_PANELS = [P_VOLUME, P_DISTRIBUTION, P_TREND, P_DISPUTED, P_HOT]

T_FROM = datetime(2026, 2, 9, tzinfo=UTC)
T_TO = datetime(2026, 2, 12, tzinfo=UTC)
GOOD_URL = "https://www.ptt.cc/bbs/Stock/M.1.A.000.html"


class QueryError(Exception):
    pass


# ---------- Grafana ----------


def grafana_url() -> str:
    url = os.environ.get("IT_GRAFANA_URL")
    if not url:
        pytest.fail("缺少 IT_GRAFANA_URL", pytrace=False)
    return url.rstrip("/")


def grafana(path: str, body: dict | None = None) -> tuple[int, dict]:
    token = base64.b64encode(f"{GRAFANA_AUTH[0]}:{GRAFANA_AUTH[1]}".encode()).decode()
    req = urllib.request.Request(
        grafana_url() + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"message": raw}


def load_dashboard() -> dict:
    status, body = grafana(f"/api/dashboards/uid/{DASHBOARD_UID}")
    assert status == 200, f"provisioning 的 dashboard {DASHBOARD_UID} 讀不到：{status} {body}"
    return body["dashboard"]


def _flatten(panels: list[dict]) -> list[dict]:
    out: list[dict] = []
    for p in panels:
        out.append(p)
        out.extend(_flatten(p.get("panels", [])))
    return out


def panel_targets(dashboard: dict, title: str) -> list[dict]:
    found = [p for p in _flatten(dashboard.get("panels", [])) if p.get("title") == title]
    assert len(found) == 1, f"面板「{title}」應剛好一個，實際 {len(found)}"
    return found[0]["targets"]


def variable(dashboard: dict, name: str) -> dict:
    found = [v for v in dashboard["templating"]["list"] if v["name"] == name]
    assert len(found) == 1
    return found[0]


def ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def ds_query(
    target: dict,
    sql: str,
    t_from: datetime = T_FROM,
    t_to: datetime = T_TO,
) -> list[dict]:
    """送一個查詢，回傳所有 frame 攤平的列（dict）；查詢錯誤丟 QueryError。"""
    query = {k: v for k, v in target.items() if k != "rawSql"}
    query.update(rawSql=sql, refId="A", datasource=DS, intervalMs=3_600_000, maxDataPoints=1000)
    status, body = grafana(
        "/api/ds/query",
        {"queries": [query], "from": str(ms(t_from)), "to": str(ms(t_to))},
    )
    result = body.get("results", {}).get("A")
    if status != 200 or result is None or result.get("error"):
        err = (result or {}).get("error") or body.get("message") or body
        raise QueryError(f"HTTP {status}: {err}")
    rows: list[dict] = []
    for frame in result.get("frames", []):
        names = [f["name"] for f in frame["schema"]["fields"]]
        columns = frame["data"]["values"]
        rows += [dict(zip(names, vals, strict=True)) for vals in zip(*columns, strict=True)]
    return rows


def ds_query_text(target: dict, sql: str) -> str:
    """frame 的欄名、labels 與所有值串成一段文字；寬表時序的看板名稱在 labels。"""
    query = {k: v for k, v in target.items() if k != "rawSql"}
    query.update(rawSql=sql, refId="A", datasource=DS, intervalMs=3_600_000, maxDataPoints=1000)
    status, body = grafana(
        "/api/ds/query",
        {"queries": [query], "from": str(ms(T_FROM)), "to": str(ms(T_TO))},
    )
    result = body.get("results", {}).get("A")
    assert status == 200 and result and not result.get("error"), body
    parts: list[str] = []
    for frame in result.get("frames", []):
        for field, vals in zip(frame["schema"]["fields"], frame["data"]["values"], strict=True):
            parts += [field["name"], json.dumps(field.get("labels") or {}, ensure_ascii=False)]
            parts += [str(v) for v in vals]
    return " ".join(parts)


def panel_text(dashboard: dict, title: str, boards: list[str], min_score: str = "0.5") -> str:
    return " ".join(
        ds_query_text(t, expand_vars(t["rawSql"], boards, min_score))
        for t in panel_targets(dashboard, title)
    )


def frames_numeric_sum(target: dict, sql: str) -> float:
    """所有 frame 裡數值欄（不含時間欄）的總和；時序與寬表都適用。"""
    query = {k: v for k, v in target.items() if k != "rawSql"}
    query.update(rawSql=sql, refId="A", datasource=DS, intervalMs=3_600_000, maxDataPoints=1000)
    status, body = grafana(
        "/api/ds/query",
        {"queries": [query], "from": str(ms(T_FROM)), "to": str(ms(T_TO))},
    )
    result = body.get("results", {}).get("A")
    assert status == 200 and result and not result.get("error"), body
    total = 0.0
    for frame in result.get("frames", []):
        for field, vals in zip(frame["schema"]["fields"], frame["data"]["values"], strict=True):
            if field["type"] == "number":
                total += sum(v for v in vals if v is not None)
    return total


# ---------- 前端變數展開的模擬 ----------


# 所有 $board、$min_score 引用只准這個格式：輸出只含 A-Z a-z 0-9 % . _ ~ -，不可能有引號或反斜線
ALLOWED_FORMATS = {"percentencode"}
FIXED_NUMBER = re.compile(r"\d(\.\d+)?")


def quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


_VAR = re.compile(
    r"\$\{(?P<a>board|min_score)(?P<ra>[^}]*)\}"
    r"|\$(?P<b>board|min_score)\b"
    r"|\[\[(?P<c>board|min_score)(?P<rc>:\w+)?\]\]"
)


@dataclass
class Ref:
    name: str
    fmt: str | None  # None = 沒指定格式；其他寫法（例 .text）原樣保留
    in_string: bool
    text: str


def _ref_at(sql: str, i: int, in_string: bool) -> tuple[Ref, int] | None:
    m = _VAR.match(sql, i)
    if not m:
        return None
    rest = (m["ra"] if m["a"] else m["rc"]) or ""
    fmt = rest[1:] if rest.startswith(":") else (rest or None)
    return Ref(m["a"] or m["b"] or m["c"], fmt, in_string, m[0]), m.end()


def references(sql: str) -> list[Ref]:
    """依序找出 $board、$min_score 的每個引用，並標出是否在 SQL 單引號內（雙引號、反引號不算）。"""
    refs: list[Ref] = []
    quote_char: str | None = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        found = _ref_at(sql, i, quote_char == "'") if ch in "$[" else None
        if found:
            refs.append(found[0])
            i = found[1]
        elif quote_char is None and sql.startswith("--", i):
            i = sql.find("\n", i) if "\n" in sql[i:] else len(sql)
        elif quote_char is None and sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = len(sql) if end < 0 else end + 2
        elif quote_char is None:
            quote_char = ch if ch in "'\"`" else None
            i += 1
        elif ch == "\\":
            i += 2
        elif ch == quote_char:
            if sql[i + 1 : i + 2] == quote_char:
                i += 2
            else:
                quote_char = None
                i += 1
        else:
            i += 1
    return refs


def _percentencode(values: list[str]) -> str:
    # Grafana 的 percentencode：多選變數的值先包成 {a,b} 再編碼（!'()* 也編碼）
    return urllib.parse.quote("{" + ",".join(values) + "}", safe="")


def grafana_format(values: list[str], fmt: str) -> str:
    """Grafana 前端對多選值的展開規則（只列測試用到的格式）。"""
    if fmt == "percentencode":
        return _percentencode(values)
    if fmt == "sqlstring":
        return ",".join("'" + v.replace("'", "''") + "'" for v in values)
    if fmt == "singlequote":
        return ",".join("'" + v.replace("'", "\\'") + "'" for v in values)
    if fmt == "csv":
        return ",".join(values)
    pytest.fail(f"測試不支援的變數格式 :{fmt}", pytrace=False)


def expand_vars(sql: str, boards: list[str], min_score: str = "0.5") -> str:
    """依引用的格式展開；min_score 是單選，percentencode 不加大括號。"""

    def var(m: re.Match) -> str:
        name = m["a"] or m["b"] or m["c"]
        fmt = (m["ra"] or m["rc"] or "").lstrip(":") or None
        values = boards if name == "board" else [min_score]
        if fmt == "percentencode" and name == "min_score":
            return urllib.parse.quote(min_score, safe="")
        if fmt:
            return grafana_format(values, fmt)
        if name == "board":
            return ",".join(quote(b) for b in values)
        return min_score

    return _VAR.sub(var, sql)


def run_panel(dashboard: dict, title: str, boards: list[str], min_score: str = "0.5") -> list[dict]:
    rows: list[dict] = []
    for target in panel_targets(dashboard, title):
        rows += ds_query(target, expand_vars(target["rawSql"], boards, min_score))
    return rows


# ---------- ClickHouse 種子資料 ----------


def ch_post(sql: str, user: str = ADMIN_USER, password: str = ADMIN_PASSWORD) -> str:
    base = os.environ["IT_CLICKHOUSE_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/?database={RADAR_DB}",
        data=sql.encode(),
        method="POST",
        headers={"X-ClickHouse-User": user, "X-ClickHouse-Key": password},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        pytest.fail(f"ClickHouse 寫入失敗：{e.read().decode()}\n{sql}", pytrace=False)


def sql_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def ts(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def new_board() -> str:
    return f"t{uuid.uuid4().hex}"


def pid(board: str, i: int = 1) -> str:
    return f"{board}.M.1.A.{i:03d}"


def title_of(post_id: str) -> str:
    return f"T[{post_id}]"


def insert_posts(rows: list[tuple[str, str, datetime]]) -> None:
    """rows: (post_id, board, created_at)；標題為 title_of(post_id)。"""
    values = ", ".join(
        f"({sql_str(p)}, {sql_str(b)}, {sql_str(title_of(p))}, '{GOOD_URL}', 0, 0, "
        f"'{ts(at)}', '{ts(at)}', 0, 1)"
        for p, b, at in rows
    )
    ch_post(
        "INSERT INTO posts_latest (post_id, board, title, url, push_count, boo_count, "
        f"created_at, crawled_at, is_deleted, lsn) VALUES {values}"
    )


def insert_comments(rows: list[tuple[str, str, int, str, datetime]]) -> None:
    """rows: (post_id, board, floor, type, commented_at)。"""
    values = ", ".join(
        f"({sql_str(p)}, {sql_str(b)}, {f}, '{t}', 'u', 'x', '{ts(at)}', "
        f"'2026-01-01 00:00:00.000', 1, 0)"
        for p, b, f, t, at in rows
    )
    ch_post(
        "INSERT INTO comments_latest (post_id, board, floor, type, user_id, content, "
        f"commented_at, changed_at, lsn, is_deleted) VALUES {values}"
    )


def votes(
    post_id: str, board: str, push: int, boo: int
) -> list[tuple[str, str, int, str, datetime]]:
    at = T_FROM + timedelta(hours=10)
    kinds = ["push"] * push + ["boo"] * boo
    return [(post_id, board, i + 1, k, at) for i, k in enumerate(kinds)]


def predict(post_id: str, polarity: str, score: float) -> None:
    rest = (1 - score) / 2
    scores = {polarity: score}
    scores.update({p: rest for p in ("negative", "neutral", "positive") if p != polarity})
    mapping = "{" + ", ".join(f"'{k}': {v}" for k, v in scores.items()) + "}"
    ch_post(
        "INSERT INTO predictions (post_id, model_version, predicted_at, polarity, scores) "
        f"VALUES ({sql_str(post_id)}, 'v1', '2026-02-01 00:00:00.000000', '{polarity}', {mapping})"
    )


@dataclass
class Seeded:
    board: str
    post_id: str


def seed_board_with_comment() -> Seeded:
    """一個看板、一篇文章（時間範圍內）、一則推文，讓 board 變數與各面板都有東西可查。"""
    board = new_board()
    p = pid(board)
    at = T_FROM + timedelta(hours=10)
    insert_posts([(p, board, at)])
    insert_comments([(p, board, 1, "push", at)])
    return Seeded(board, p)

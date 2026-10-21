"""驗收 dashboard-views（開發規格 7.25「查詢來源」）：post_votes、post_sentiment_latest。

種子資料放 radar DB（管理帳號寫入），以唯讀帳號查 view；看板名稱帶 uuid，斷言只看自己的看板，
標 xdist_group("shared_radar_db")，避免被 cdc 模組 TRUNCATE 清掉（#111）。
測試帳密與 compose.yaml 一致，不讀 .env。
"""

import json
import os
import urllib.error
import urllib.request
import uuid

import pytest

pytestmark = pytest.mark.xdist_group("shared_radar_db")

RO_USER = os.environ.get("CLICKHOUSE_GRAFANA_USER", "grafana")
RO_PASSWORD = os.environ.get("CLICKHOUSE_GRAFANA_PASSWORD", "it")
ADMIN_USER, ADMIN_PASSWORD = "radar", "it"
RADAR_DB = "radar"
T0 = "2026-01-01 00:00:00.000000"


def _post(sql: str, user: str, password: str) -> tuple[int, str]:
    base = os.environ["IT_CLICKHOUSE_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/?database={RADAR_DB}",
        data=sql.encode(),
        method="POST",
        headers={"X-ClickHouse-User": user, "X-ClickHouse-Key": password},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode().strip()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode().strip()


def _admin(sql: str) -> None:
    status, body = _post(sql, ADMIN_USER, ADMIN_PASSWORD)
    assert status == 200, body


def _query(sql: str) -> list[dict]:
    """以唯讀帳號查，回傳每列一個 dict。"""
    status, body = _post(f"{sql} FORMAT JSONEachRow", RO_USER, RO_PASSWORD)
    assert status == 200, body
    return [json.loads(line) for line in body.splitlines() if line]


def _board() -> str:
    return f"t{uuid.uuid4().hex}"


def _post_id(board: str, name: str = "M.1.A.000") -> str:
    return f"{board}.{name}"


def _comment(
    post_id: str, board: str, floor: int, ctype: str, lsn: int = 1, deleted: int = 0
) -> str:
    return (
        f"('{post_id}', '{board}', {floor}, '{ctype}', 'u', 'x', '{T0}', "
        f"'2026-01-01 00:00:00.000', {lsn}, {deleted})"
    )


def _insert_comments(rows: list[str]) -> None:
    _admin(
        "INSERT INTO comments_latest (post_id, board, floor, type, user_id, content, "
        "commented_at, changed_at, lsn, is_deleted) VALUES " + ", ".join(rows)
    )


def _insert_prediction(
    post_id: str, version: str, predicted_at: str, polarity: str, scores: dict[str, float]
) -> None:
    mapping = "{" + ", ".join(f"'{k}': {v}" for k, v in scores.items()) + "}"
    _admin(
        "INSERT INTO predictions (post_id, model_version, predicted_at, polarity, scores) "
        f"VALUES ('{post_id}', '{version}', '{predicted_at}', '{polarity}', {mapping})"
    )


def _votes(board: str) -> dict[str, dict]:
    rows = _query(f"SELECT * FROM post_votes WHERE board = '{board}'")
    return {r["post_id"]: r for r in rows}


def _sentiments(post_ids: list[str]) -> list[dict]:
    ids = ", ".join(f"'{p}'" for p in post_ids)
    return _query(f"SELECT * FROM post_sentiment_latest WHERE post_id IN ({ids})")


# ---------- view 本身 ----------


@pytest.mark.parametrize("name", ["post_votes", "post_sentiment_latest"])
def test_view_is_plain_view_not_materialized(name: str) -> None:
    rows = _query(f"SELECT engine FROM system.tables WHERE database = 'radar' AND name = '{name}'")
    assert rows == [{"engine": "View"}]


def test_post_votes_exposes_documented_columns() -> None:
    rows = _query("SELECT name FROM system.columns WHERE database='radar' AND table='post_votes'")
    assert {r["name"] for r in rows} == {"post_id", "board", "push", "boo", "arrow"}


def test_post_sentiment_latest_exposes_documented_columns() -> None:
    rows = _query(
        "SELECT name FROM system.columns WHERE database='radar' AND table='post_sentiment_latest'"
    )
    assert {r["name"] for r in rows} == {"post_id", "model_version", "polarity", "score"}


def test_readonly_user_cannot_modify_views() -> None:
    status, _ = _post("DROP VIEW post_votes", RO_USER, RO_PASSWORD)
    assert status != 200
    assert _query("SELECT count() AS n FROM system.tables WHERE name = 'post_votes'") == [{"n": 1}]


# ---------- post_votes ----------


def test_post_votes_counts_each_type_per_post() -> None:
    board = _board()
    pid = _post_id(board)
    _insert_comments(
        [
            _comment(pid, board, 1, "push"),
            _comment(pid, board, 2, "push"),
            _comment(pid, board, 3, "push"),
            _comment(pid, board, 4, "boo"),
            _comment(pid, board, 5, "boo"),
            _comment(pid, board, 6, "arrow"),
        ]
    )
    row = _votes(board)[pid]
    assert (int(row["push"]), int(row["boo"]), int(row["arrow"])) == (3, 2, 1)
    assert row["board"] == board


def test_post_votes_one_row_per_post() -> None:
    board = _board()
    a, b = _post_id(board, "M.1.A.001"), _post_id(board, "M.1.A.002")
    _insert_comments([_comment(a, board, 1, "push"), _comment(b, board, 1, "boo")])
    votes = _votes(board)
    assert set(votes) == {a, b}
    assert (int(votes[a]["push"]), int(votes[a]["boo"])) == (1, 0)
    assert (int(votes[b]["push"]), int(votes[b]["boo"])) == (0, 1)


def test_post_votes_excludes_deleted_comments() -> None:
    board = _board()
    pid = _post_id(board)
    _insert_comments(
        [
            _comment(pid, board, 1, "push"),
            _comment(pid, board, 2, "push"),
            _comment(pid, board, 3, "boo"),
            # 第 2 層之後被刪除：同 (post_id, floor) 較新的 lsn、is_deleted=1
            _comment(pid, board, 2, "push", lsn=2, deleted=1),
        ]
    )
    row = _votes(board)[pid]
    assert (int(row["push"]), int(row["boo"]), int(row["arrow"])) == (1, 1, 0)


def test_post_votes_does_not_count_post_with_only_deleted_comments() -> None:
    board = _board()
    pid = _post_id(board)
    _insert_comments(
        [
            _comment(pid, board, 1, "push"),
            _comment(pid, board, 1, "push", lsn=2, deleted=1),
        ]
    )
    row = _votes(board).get(pid)
    assert row is None or (int(row["push"]), int(row["boo"]), int(row["arrow"])) == (0, 0, 0)


def test_post_votes_uses_latest_version_of_edited_comment() -> None:
    board = _board()
    pid = _post_id(board)
    _insert_comments(
        [
            _comment(pid, board, 1, "push", lsn=1),
            # 推文被改成噓：較新的 lsn 取代舊的，不能兩邊都算
            _comment(pid, board, 1, "boo", lsn=5),
        ]
    )
    row = _votes(board)[pid]
    assert (int(row["push"]), int(row["boo"]), int(row["arrow"])) == (0, 1, 0)


def test_post_votes_ignores_older_lsn_arriving_late() -> None:
    board = _board()
    pid = _post_id(board)
    _insert_comments([_comment(pid, board, 1, "boo", lsn=5)])
    _insert_comments([_comment(pid, board, 1, "push", lsn=1)])
    row = _votes(board)[pid]
    assert (int(row["push"]), int(row["boo"])) == (0, 1)


def test_post_votes_does_not_mix_other_boards() -> None:
    mine, other = _board(), _board()
    pid, other_pid = _post_id(mine), _post_id(other)
    _insert_comments([_comment(pid, mine, 1, "push"), _comment(other_pid, other, 1, "push")])
    assert set(_votes(mine)) == {pid}


def test_post_votes_post_without_comments_does_not_appear() -> None:
    board = _board()
    pid = _post_id(board)
    _admin(
        "INSERT INTO posts_latest (post_id, board, title, url, push_count, boo_count, "
        f"created_at, crawled_at, is_deleted, lsn) VALUES ('{pid}', '{board}', 't', "
        f"'https://www.ptt.cc/x', 0, 0, '{T0}', '{T0}', 0, 1)"
    )
    assert _votes(board) == {}


# ---------- post_sentiment_latest ----------


def test_sentiment_latest_returns_polarity_and_max_score() -> None:
    pid = _post_id(_board())
    _insert_prediction(
        pid, "v1", T0, "negative", {"negative": 0.7, "neutral": 0.2, "positive": 0.1}
    )
    (row,) = _sentiments([pid])
    assert row["post_id"] == pid
    assert row["model_version"] == "v1"
    assert row["polarity"] == "negative"
    assert float(row["score"]) == pytest.approx(0.7)


def test_sentiment_latest_takes_most_recent_prediction() -> None:
    pid = _post_id(_board())
    _insert_prediction(
        pid, "v1", "2026-01-01 00:00:00.000000", "negative", {"negative": 0.9, "positive": 0.1}
    )
    _insert_prediction(
        pid, "v1", "2026-01-02 00:00:00.000000", "positive", {"negative": 0.3, "positive": 0.6}
    )
    (row,) = _sentiments([pid])
    assert row["polarity"] == "positive"
    assert float(row["score"]) == pytest.approx(0.6)


def test_sentiment_latest_newest_wins_even_if_inserted_first() -> None:
    pid = _post_id(_board())
    _insert_prediction(
        pid, "v2", "2026-03-01 00:00:00.000000", "neutral", {"negative": 0.2, "neutral": 0.8}
    )
    _insert_prediction(
        pid, "v1", "2026-01-01 00:00:00.000000", "negative", {"negative": 0.9, "neutral": 0.1}
    )
    (row,) = _sentiments([pid])
    assert row["polarity"] == "neutral"
    assert row["model_version"] == "v2"
    assert float(row["score"]) == pytest.approx(0.8)


def test_sentiment_latest_one_row_per_post_across_model_versions() -> None:
    board = _board()
    a, b = _post_id(board, "M.1.A.001"), _post_id(board, "M.1.A.002")
    for version, day in (("v1", "01"), ("v2", "02"), ("v3", "03")):
        at = f"2026-01-{day} 00:00:00.000000"
        _insert_prediction(a, version, at, "neutral", {"neutral": 0.5})
    _insert_prediction(b, "v1", T0, "positive", {"positive": 0.95})
    rows = _sentiments([a, b])
    assert sorted(r["post_id"] for r in rows) == sorted([a, b])
    by_post = {r["post_id"]: r for r in rows}
    assert by_post[a]["model_version"] == "v3"
    assert by_post[b]["polarity"] == "positive"


def test_sentiment_latest_omits_post_without_prediction() -> None:
    board = _board()
    with_pred, without = _post_id(board, "M.1.A.001"), _post_id(board, "M.1.A.002")
    _insert_prediction(with_pred, "v1", T0, "neutral", {"neutral": 0.6})
    _admin(
        "INSERT INTO posts_latest (post_id, board, title, url, push_count, boo_count, "
        f"created_at, crawled_at, is_deleted, lsn) VALUES ('{without}', '{board}', 't', "
        f"'https://www.ptt.cc/x', 0, 0, '{T0}', '{T0}', 0, 1)"
    )
    rows = _sentiments([with_pred, without])
    assert [r["post_id"] for r in rows] == [with_pred]


def test_sentiment_latest_score_is_max_of_all_classes() -> None:
    pid = _post_id(_board())
    # NOTE: 三類最高分在最後一個 key，確認不是取第一個值
    _insert_prediction(
        pid, "v1", T0, "positive", {"negative": 0.05, "neutral": 0.15, "positive": 0.8}
    )
    (row,) = _sentiments([pid])
    assert float(row["score"]) == pytest.approx(0.8)


def test_sentiment_latest_uncertain_boundary_score_is_kept_as_is() -> None:
    # 低於 min_score 的歸類在面板做；view 不過濾，也不改 polarity
    pid = _post_id(_board())
    _insert_prediction(
        pid, "v1", T0, "neutral", {"negative": 0.34, "neutral": 0.35, "positive": 0.31}
    )
    (row,) = _sentiments([pid])
    assert row["polarity"] == "neutral"
    assert float(row["score"]) == pytest.approx(0.35)

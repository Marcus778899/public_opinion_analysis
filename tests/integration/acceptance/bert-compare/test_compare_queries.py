"""bert-compare 驗收：compare 的查詢與指標對預先寫入的資料算出預期值（開發規格 7.27）。

預期值為手算；a 在 predictions，b 在 predictions_shadow。
"""

import csv
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.settings import InferenceRole
from radar.ml.labeling.prompt import PROMPT_VERSION
from radar.ml.training import compare

A = "bert-a"
B = "bert-b"
LABELER = "groq:q"
SINCE = datetime(2026, 10, 10, tzinfo=UTC)
BASE = datetime(2026, 10, 11, tzinfo=UTC)
P, N, U = Polarity.POSITIVE, Polarity.NEGATIVE, Polarity.NEUTRAL

# post_id: (board, title, created_at, (a 類別, a 信心), (b 類別, b 信心), LLM 標註)
PAIRS = {
    "Stock.M.1.A.1": ("Stock", "s1", "2026-10-10 00:00:00", (P, 0.95), (P, 0.90), P),
    "Stock.M.2.A.1": ("Stock", "s2", "2026-10-11 00:00:00", (N, 0.80), (N, 0.65), N),
    "Stock.M.3.A.1": ("Stock", "s3", "2026-10-11 00:00:00", (U, 0.55), (P, 0.45), U),
    "Stock.M.4.A.1": ("Stock", '標題,含"逗號"', "2026-10-11 00:00:00", (P, 0.45), (N, 0.35), None),
    "Gossiping.M.1.A.1": ("Gossiping", "g1", "2026-10-11 00:00:00", (N, 0.75), (N, 0.55), N),
    "Gossiping.M.2.A.1": ("Gossiping", "g2", "2026-10-11 00:00:00", (U, 0.60), (U, 0.38), U),
    "Gossiping.M.3.A.1": ("Gossiping", "g3", "2026-10-11 00:00:00", (P, 0.85), (U, 0.52), P),
}
DISAGREE = {"Stock.M.3.A.1", "Stock.M.4.A.1", "Gossiping.M.3.A.1"}


def scores_sql(polarity: Polarity, top: float) -> str:
    rest = (1 - top) / 2
    items = [(p.value, top if p is polarity else rest) for p in Polarity]
    return "map(" + ", ".join(f"'{k}', {v}" for k, v in items) + ")"


def insert_predictions(
    client: ClickHouseClient, table: str, rows: list[tuple[str, str, datetime, Polarity, float]]
) -> None:
    values = ", ".join(
        f"('{pid}', '{ver}', '{at:%Y-%m-%d %H:%M:%S.%f}', '{pol.value}', {scores_sql(pol, top)})"
        for pid, ver, at, pol, top in rows
    )
    client.execute(
        f"INSERT INTO {table} (post_id, model_version, predicted_at, polarity, scores) "
        f"VALUES {values}"
    )


def seed_pairs(client: ClickHouseClient) -> None:
    ts = "'2026-10-11 00:00:00'"
    posts = [
        f"('{pid}', '{board}', '{title.replace('"', '\\"')}', 'c', 'u', 0, 0, '{created}', "
        f"{ts}, false, 1)"
        for pid, (board, title, created, *_rest) in PAIRS.items()
    ]
    posts += [
        # 太舊、已刪除（較新的 lsn 蓋掉）、只有一版有預測的文章都不該出現
        f"('Stock.M.old.A.1', 'Stock', 'old', 'c', 'u', 0, 0, '2026-10-09 23:59:59', {ts}, "
        "false, 1)",
        f"('Stock.M.del.A.1', 'Stock', 'del', 'c', 'u', 0, 0, {ts}, {ts}, false, 1)",
        f"('Stock.M.del.A.1', 'Stock', 'del', 'c', 'u', 0, 0, {ts}, {ts}, true, 2)",
        f"('Stock.M.onlya.A.1', 'Stock', 'oa', 'c', 'u', 0, 0, {ts}, {ts}, false, 1)",
        f"('Stock.M.onlyb.A.1', 'Stock', 'ob', 'c', 'u', 0, 0, {ts}, {ts}, false, 1)",
    ]
    client.execute(
        "INSERT INTO posts_latest (post_id, board, title, content, url, push_count, boo_count, "
        "created_at, crawled_at, is_deleted, lsn) VALUES " + ", ".join(posts)
    )

    early, late = BASE, BASE + timedelta(hours=1)
    a_rows = [(pid, A, late, v[3][0], v[3][1]) for pid, v in PAIRS.items()]
    b_rows = [(pid, B, late, v[4][0], v[4][1]) for pid, v in PAIRS.items()]
    # 同一篇取最新一筆：Gossiping.M.3 的 a 先預測 negative，之後改成 positive
    a_rows.append(("Gossiping.M.3.A.1", A, early, N, 0.99))
    # 別的版本、不在兩邊的文章、太舊與已刪除的文章
    a_rows.append(("Stock.M.1.A.1", "bert-x", late, N, 0.99))
    b_rows.append(("Stock.M.1.A.1", "bert-x", late, N, 0.99))
    for pid in ("Stock.M.old.A.1", "Stock.M.del.A.1"):
        a_rows.append((pid, A, late, P, 0.9))
        b_rows.append((pid, B, late, N, 0.9))
    a_rows.append(("Stock.M.onlya.A.1", A, late, P, 0.9))
    b_rows.append(("Stock.M.onlyb.A.1", B, late, P, 0.9))
    insert_predictions(client, "predictions", a_rows)
    insert_predictions(client, "predictions_shadow", b_rows)

    labels = [
        (pid, LABELER, PROMPT_VERSION, "2026-10-11 02:00:00", None, v[5].value)
        for pid, v in PAIRS.items()
        if v[5] is not None
    ]
    # 重標取最新；其他標註者、其他版本、針對標的（target 非 NULL）的標註都不算
    labels.append(
        ("Stock.M.3.A.1", LABELER, PROMPT_VERSION, "2026-10-11 01:00:00", None, "negative")
    )
    labels.append(
        ("Stock.M.4.A.1", "manual", PROMPT_VERSION, "2026-10-11 02:00:00", None, "negative")
    )
    labels.append(
        ("Gossiping.M.2.A.1", LABELER, PROMPT_VERSION, "2026-10-11 03:00:00", "X", "negative")
    )
    labels.append(("Stock.M.1.A.1", LABELER, "old-prompt", "2026-10-11 03:00:00", None, "negative"))
    values = ", ".join(
        f"('{p}', '{lab}', '{ver}', '{ts}', {'NULL' if t is None else repr(t)}, '{pol}')"
        for p, lab, ver, ts, t, pol in labels
    )
    client.execute(
        f"INSERT INTO labels (post_id, labeler, version, labeled_at, target, polarity) "
        f"VALUES {values}"
    )


def history_row(pid: str, op: str, changed_at: datetime, lsn: int) -> str:
    ts = "'2026-10-10 12:00:00'"
    at = f"{changed_at:%Y-%m-%d %H:%M:%S.%f}"
    return f"('{pid}', 'Stock', 't', 0, 0, {ts}, {ts}, false, '{op}', '{at}', {lsn})"


def seed_latency(client: ClickHouseClient) -> None:
    sec = timedelta(seconds=1)
    history = []
    shadow = []
    for i in range(1, 22):
        pid = f"Lat.b.{i:02d}"
        history.append(history_row(pid, "c", BASE, i))
        shadow.append((pid, B, BASE + i * sec, N, 0.6))
    # 同一篇之後又預測一次：只算第一次
    shadow.append(("Lat.b.01", B, BASE + 100 * sec, N, 0.6))
    # 該篇之後的 update 不影響起點；別的版本的預測不算
    history.append(history_row("Lat.b.02", "u", BASE + sec // 2, 99))
    shadow.append(("Lat.b.05", "bert-x", BASE + 500 * sec, N, 0.6))
    # changed_at 早於 since、只有 update 沒有 create 的文章不算
    history.append(history_row("Lat.b.old", "c", SINCE - sec, 1))
    shadow.append(("Lat.b.old", B, SINCE + 1000 * sec, N, 0.6))
    history.append(history_row("Lat.b.upd", "u", BASE, 1))
    shadow.append(("Lat.b.upd", B, BASE + 50 * sec, N, 0.6))
    primary = []
    for i, d in enumerate((5, 6, 7), start=1):
        pid = f"Lat.a.{i}"
        history.append(history_row(pid, "c", BASE, i))
        primary.append((pid, A, BASE + d * sec, N, 0.6))
    client.execute(
        "INSERT INTO posts_history (post_id, board, title, push_count, boo_count, created_at, "
        "crawled_at, is_deleted, op, changed_at, lsn) VALUES " + ", ".join(history)
    )
    insert_predictions(client, "predictions_shadow", shadow)
    insert_predictions(client, "predictions", primary)


@pytest.fixture(scope="module")
def ch(clickhouse):
    seed_pairs(clickhouse)
    seed_latency(clickhouse)
    return clickhouse


@pytest.fixture(scope="module")
def pairs(ch) -> list[compare.PairedPrediction]:
    got = compare.fetch_pairs(ch, A, B, SINCE, LABELER, PROMPT_VERSION)
    return sorted(got, key=lambda p: p.post_id)


def test_fetch_pairs_keeps_only_live_posts_since_with_both_versions(pairs):
    assert [p.post_id for p in pairs] == sorted(PAIRS)


def test_fetch_pairs_returns_board_title_and_latest_prediction_of_each_version(pairs):
    by_id = {p.post_id: p for p in pairs}
    for pid, (board, title, _created, a, b, _llm) in PAIRS.items():
        p = by_id[pid]
        assert (p.board, p.title) == (board, title)
        assert (p.polarity_a, p.polarity_b) == (a[0], b[0])
        assert p.score_a == pytest.approx(a[1])
        assert p.score_b == pytest.approx(b[1])


def test_fetch_pairs_joins_only_whole_post_labels_of_primary_labeler_and_current_version(pairs):
    llm = {p.post_id: p.llm for p in pairs}
    assert llm == {pid: v[5] for pid, v in PAIRS.items()}


def test_fetch_pairs_with_no_overlap_returns_empty(ch):
    got = compare.fetch_pairs(ch, A, "bert-none", SINCE, LABELER, PROMPT_VERSION)

    assert got == []


def test_agreement_overall_computes_accuracy_kappa_and_confusion(pairs):
    stats = compare.agreement(pairs)

    assert stats.n == 7
    assert stats.accuracy == pytest.approx(4 / 7)
    assert stats.cohen_kappa == pytest.approx(12 / 33)
    expected = {(P, P): 1, (N, N): 2, (U, U): 1, (U, P): 1, (P, N): 1, (P, U): 1}
    for pa in Polarity:
        for pb in Polarity:
            assert stats.confusion[pa][pb] == expected.get((pa, pb), 0)


def test_agreement_by_board_computes_each_board_separately(pairs):
    stock = compare.agreement([p for p in pairs if p.board == "Stock"])
    gossip = compare.agreement([p for p in pairs if p.board == "Gossiping"])

    assert (stock.n, stock.accuracy, stock.cohen_kappa) == (4, 0.5, pytest.approx(0.2))
    assert (gossip.n, gossip.accuracy, gossip.cohen_kappa) == (3, pytest.approx(2 / 3), 0.5)
    assert stock.confusion[P][N] == 1 and stock.confusion[U][P] == 1
    assert gossip.confusion[P][U] == 1 and gossip.confusion[U][U] == 1


def test_fetch_latency_shadow_computes_percentiles_from_first_prediction_after_create(ch):
    stats = compare.fetch_latency(ch, B, InferenceRole.SHADOW, SINCE)

    assert stats.n == 21
    assert stats.p50_s == pytest.approx(11.0)
    assert stats.p95_s == pytest.approx(20.0)
    assert stats.max_s == pytest.approx(21.0)


def test_fetch_latency_primary_reads_predictions_table(ch):
    stats = compare.fetch_latency(ch, A, InferenceRole.PRIMARY, SINCE)

    assert stats.n == 3
    assert stats.p50_s == pytest.approx(6.0)
    assert stats.max_s == pytest.approx(7.0)


def test_fetch_latency_model_not_in_role_table_returns_zero_posts(ch):
    assert compare.fetch_latency(ch, A, InferenceRole.SHADOW, SINCE).n == 0


def test_confidence_buckets_compute_below_ratio_and_accuracy_at_or_above_threshold():
    scores = [(0.9, True), (0.65, True), (0.55, False), (0.5, False), (0.45, None), (0.35, True)]

    buckets = {b.threshold: b for b in compare.confidence_buckets(scores)}

    assert sorted(buckets) == [0.4, 0.5, 0.6, 0.7]
    below = {t: b.below_ratio for t, b in buckets.items()}
    assert below == pytest.approx({0.4: 1 / 6, 0.5: 2 / 6, 0.6: 4 / 6, 0.7: 5 / 6})
    assert {t: b.n_vs_llm for t, b in buckets.items()} == {0.4: 4, 0.5: 4, 0.6: 2, 0.7: 1}
    acc = {t: b.accuracy_vs_llm for t, b in buckets.items()}
    assert acc == pytest.approx({0.4: 0.5, 0.5: 0.5, 0.6: 1.0, 0.7: 1.0})


def test_confidence_buckets_from_pairs_use_top_score_of_each_version(pairs):
    scores_b = [(p.score_b, None if p.llm is None else p.polarity_b == p.llm) for p in pairs]

    buckets = {b.threshold: b for b in compare.confidence_buckets(scores_b)}

    # b 的信心：0.90 0.65 0.45 0.35 0.55 0.38 0.52；低於 0.4 的是 0.35、0.38
    assert buckets[0.4].below_ratio == pytest.approx(2 / 7)
    assert buckets[0.7].below_ratio == pytest.approx(6 / 7)


def test_write_disagreements_writes_only_differing_pairs_as_csv(tmp_path, pairs):
    path = tmp_path / "disagreements.csv"

    count = compare.write_disagreements(path, pairs)

    assert count == 3
    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines(keepends=True)))
    body = rows[1:]  # 第一列是欄名
    assert len(body) == 3
    by_id = {next(c for c in row if c in PAIRS): row for row in body}
    assert set(by_id) == DISAGREE
    # 標題含逗號與引號，CSV 讀回要原樣
    assert '標題,含"逗號"' in by_id["Stock.M.4.A.1"]
    assert {"neutral", "positive"} <= set(by_id["Stock.M.3.A.1"])
    assert "None" not in by_id["Stock.M.4.A.1"]


def test_write_disagreements_no_difference_returns_zero(tmp_path, pairs):
    same = [p for p in pairs if p.post_id not in DISAGREE]

    assert compare.write_disagreements(tmp_path / "d.csv", same) == 0


def test_main_writes_comparison_report_and_disagreement_csv(
    ch, worker_clickhouse_settings, tmp_path, monkeypatch
):
    s = worker_clickhouse_settings
    for key, value in {
        "CLICKHOUSE_URL": s.url,
        "CLICKHOUSE_DB": s.db,
        "CLICKHOUSE_USER": s.user,
        "CLICKHOUSE_PASSWORD": s.password.get_secret_value(),
        "LABEL_PRIMARY": "groq",
        "GROQ_API_KEY": "unused",
        "GROQ_MODEL": "q",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(tmp_path)
    argv = ["compare", "--a", A, "--b", B, "--since", "2026-10-10T00:00:00+00:00"]
    monkeypatch.setattr(sys, "argv", argv)

    compare.main()

    report = Path(tmp_path / "models" / B / "comparison.md").read_text(encoding="utf-8")
    assert A in report and B in report
    # 一致率 4/7、kappa 12/33、各看板；macro-F1：a 對 LLM 全對 1.000、b 為 0.667，皆 6 篇
    assert "57.1%" in report or "0.571" in report
    assert "0.364" in report
    assert "Stock" in report and "Gossiping" in report
    assert "0.667" in report and "1.000" in report
    csv_path = tmp_path / "data" / "review" / f"disagreements-{A}-vs-{B}.csv"
    assert len(csv_path.read_text(encoding="utf-8").splitlines()) >= 4

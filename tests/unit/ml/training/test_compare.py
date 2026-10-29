import csv
from datetime import UTC, datetime, timedelta, timezone

import pytest

from radar.common.enums import Polarity
from radar.common.settings import InferenceRole
from radar.ml.training import compare

P, N, U = Polarity.POSITIVE, Polarity.NEGATIVE, Polarity.NEUTRAL
SINCE = datetime(2026, 10, 10, tzinfo=UTC)


class FakeClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def query_rows(self, sql, params=None):
        self.calls.append((sql, params))
        return self.rows


def pair(pid, board, a, b, llm=None, sa=0.9, sb=0.8, title="t"):
    return compare.PairedPrediction(pid, board, title, a, sa, b, sb, llm)


def test_fetch_pairs_converts_rows_and_passes_all_values_as_params():
    row = {
        "post_id": "Stock.M.1.A.1",
        "board": "Stock",
        "title": "x",
        "polarity_a": "positive",
        "score_a": 0.9,
        "polarity_b": "negative",
        "score_b": 0.6,
        "llm": "",
    }
    client = FakeClient([row])
    plus8 = datetime(2026, 10, 10, 8, tzinfo=timezone(timedelta(hours=8)))

    got = compare.fetch_pairs(client, "va", "vb'; DROP", plus8, "groq:q", "v1")

    assert got == [pair("Stock.M.1.A.1", "Stock", P, N, None, 0.9, 0.6, "x")]
    sql, params = client.calls[0]
    assert "vb'" not in sql and "predictions_shadow" in sql
    assert params["version_b"] == "vb'; DROP"
    assert params["since"] == "2026-10-10 00:00:00.000000"


def test_fetch_pairs_label_present_is_parsed_as_polarity():
    row = {
        "post_id": "a",
        "board": "b",
        "title": "",
        "polarity_a": "neutral",
        "score_a": 0.5,
        "polarity_b": "neutral",
        "score_b": 0.5,
        "llm": "negative",
    }

    assert compare.fetch_pairs(FakeClient([row]), "a", "b", SINCE, "l", "v")[0].llm is N


def test_fetch_latency_computes_percentiles_with_interpolation():
    client = FakeClient([{"latency_s": str(i)} for i in range(1, 22)])

    stats = compare.fetch_latency(client, "vb", InferenceRole.SHADOW, SINCE)

    assert (stats.n, stats.p50_s, stats.p95_s, stats.max_s) == (21, 11.0, 20.0, 21.0)
    assert "FROM predictions_shadow" in client.calls[0][0]


def test_fetch_latency_primary_role_reads_predictions_table():
    client = FakeClient([{"latency_s": 1.0}])

    compare.fetch_latency(client, "va", InferenceRole.PRIMARY, SINCE)

    assert "FROM predictions\n" in client.calls[0][0]


def test_fetch_latency_no_rows_returns_zeros():
    stats = compare.fetch_latency(FakeClient([]), "v", InferenceRole.SHADOW, SINCE)

    assert (stats.n, stats.p50_s, stats.p95_s, stats.max_s) == (0, 0.0, 0.0, 0.0)


def test_percentile_single_value_returns_it():
    assert compare.percentile([3.0], 0.95) == 3.0


def test_agreement_counts_confusion_accuracy_and_kappa():
    pairs = [pair("1", "S", P, P), pair("2", "S", N, N), pair("3", "S", U, P), pair("4", "S", P, N)]

    st = compare.agreement(pairs)

    assert st.n == 4 and st.accuracy == 0.5
    assert st.confusion[U][P] == 1 and st.confusion[P][N] == 1 and st.confusion[N][N] == 1
    assert -1 <= st.cohen_kappa <= 1


def test_agreement_empty_returns_zeros():
    st = compare.agreement([])

    assert (st.n, st.accuracy, st.cohen_kappa) == (0, 0.0, 0.0)
    assert st.confusion[P][P] == 0


def test_agreement_single_class_identical_has_kappa_one():
    st = compare.agreement([pair("1", "S", P, P), pair("2", "S", P, P)])

    assert st.cohen_kappa == 1.0


def test_confidence_buckets_empty_returns_zero_buckets():
    buckets = compare.confidence_buckets([])

    assert [b.threshold for b in buckets] == [0.4, 0.5, 0.6, 0.7]
    assert all(b.below_ratio == 0 and b.n_vs_llm == 0 for b in buckets)


def test_confidence_buckets_threshold_is_inclusive_for_accuracy():
    b = {x.threshold: x for x in compare.confidence_buckets([(0.5, True), (0.49, False)])}

    assert b[0.5].n_vs_llm == 1 and b[0.5].accuracy_vs_llm == 1.0
    assert b[0.5].below_ratio == 0.5


def test_macro_f1_vs_llm_skips_unlabelled_posts():
    pairs = [pair("1", "S", P, N, P), pair("2", "S", N, N, N), pair("3", "S", P, P, None)]

    f1_a, n_a = compare.macro_f1_vs_llm(pairs, use_b=False)
    f1_b, n_b = compare.macro_f1_vs_llm(pairs, use_b=True)

    assert (n_a, n_b) == (2, 2)
    assert f1_a == pytest.approx(2 / 3)  # P、N 為 1，U 無樣本為 0
    assert f1_b < f1_a


def test_macro_f1_vs_llm_without_labels_returns_zero():
    assert compare.macro_f1_vs_llm([pair("1", "S", P, N)], use_b=True) == (0.0, 0)


def test_render_markdown_lists_versions_boards_and_formatted_numbers():
    pairs = [pair("1", "Stock", P, P), pair("2", "Gossiping", N, U)]
    overall = compare.agreement(pairs)
    by_board = {"Stock": compare.agreement(pairs[:1]), "Gossiping": compare.agreement(pairs[1:])}
    lat = compare.LatencyStats(2, 1.5, 2.0, 3.0)
    conf = {"va": compare.confidence_buckets([(0.9, True)]), "vb": []}

    text = compare.render_markdown("va", "vb", overall, by_board, {"va": lat, "vb": lat}, conf)

    assert "va vs vb" in text and "50.0%" in text
    assert "Stock" in text and "Gossiping" in text
    assert "1.500" in text and "3.000" in text


def test_render_llm_section_reports_f1_and_counts_for_both_versions():
    pairs = [pair("1", "S", P, N, P), pair("2", "S", N, N, N)]

    text = compare.render_llm_section("va", "vb", pairs)

    assert "| va | 0.667 | 2 |" in text
    assert "| vb |" in text


def test_write_disagreements_writes_header_and_only_differing_rows(tmp_path):
    pairs = [pair("1", "S", P, P), pair("2", "S", N, U, None, title='a,"b"')]
    path = tmp_path / "sub" / "d.csv"

    count = compare.write_disagreements(path, pairs)

    rows = list(csv.reader(path.read_text(encoding="utf-8").splitlines(keepends=True)))
    assert count == 1 and len(rows) == 2
    assert rows[1][:3] == ["2", "S", 'a,"b"'] and rows[1][-1] == ""


def test_write_disagreements_none_writes_header_only(tmp_path):
    path = tmp_path / "d.csv"

    assert compare.write_disagreements(path, [pair("1", "S", P, P)]) == 0
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_model_version_arg_rejects_bad_format():
    import argparse

    import pytest

    from radar.ml.training.compare import model_version_arg

    assert model_version_arg("bert-a-1") == "bert-a-1"
    with pytest.raises(argparse.ArgumentTypeError):
        model_version_arg("Bad Version")

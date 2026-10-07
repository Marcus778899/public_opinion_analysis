import csv

import pytest

from radar.common.enums import Polarity
from radar.ml.labeling.cross_check import (
    CSV_FIELDS,
    AgreementSummary,
    Disagreement,
    compare,
    fetch_whole_post_labels,
    kappa,
    post_url,
    write_disagreements_csv,
)
from radar.ml.labeling.prompt import PostText
from tests.unit.ml.fakes import FakeClickHouse

POS, NEU, NEG = Polarity.POSITIVE, Polarity.NEUTRAL, Polarity.NEGATIVE


def test_fetch_whole_post_labels_uses_params():
    ch = FakeClickHouse([{"post_id": "a", "polarity": "negative"}])

    labels = fetch_whole_post_labels(ch, "groq:q", "prompt-v4")

    assert labels == {"a": NEG}
    sql, params = ch.queries[0]
    assert "target IS NULL" in sql and "argMax(polarity, labeled_at)" in sql
    assert params == {"labeler": "groq:q", "version": "prompt-v4"}


def test_compare_counts_only_overlap():
    summary, _ = compare({"a": POS, "b": NEG, "only-primary": NEU}, {"a": POS, "b": NEG, "x": POS})

    assert (summary.overlap, summary.agreed, summary.rate) == (2, 2, 1.0)


def test_compare_lists_disagreements():
    summary, rows = compare({"a": POS, "b": NEG, "c": NEU}, {"a": POS, "b": NEU, "c": NEU})

    assert rows == [Disagreement("b", NEG, NEU)]
    assert summary.agreed == 2
    assert 0 < summary.cohen_kappa < 1


def test_compare_no_overlap_returns_zero_summary():
    summary, rows = compare({"a": POS}, {"b": POS})

    assert summary == AgreementSummary(overlap=0, agreed=0, cohen_kappa=0.0)
    assert summary.rate == 0.0 and rows == []


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [([NEU, NEU], [NEU, NEU], 1.0), ([NEU, NEU], [NEG, NEG], 0.0), ([], [], 0.0)],
)
def test_kappa_single_class_or_empty_is_not_nan(a, b, expected):
    assert kappa(a, b) == expected


def test_post_url():
    assert post_url("Stock.M.1759730000.A.1B2") == (
        "https://www.ptt.cc/bbs/Stock/M.1759730000.A.1B2.html"
    )


def test_write_disagreements_csv_has_header_and_blank_human_column(tmp_path):
    path = tmp_path / "review" / "d.csv"
    pid = "Stock.M.1759730000.A.1B2"
    posts = {pid: PostText(pid, "Stock", "台積電法說", "c")}

    write_disagreements_csv([Disagreement(pid, NEG, NEU)], posts, path)

    with path.open(encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == CSV_FIELDS
    assert rows[0]["title"] == "台積電法說"
    assert (rows[0]["primary"], rows[0]["secondary"], rows[0]["human"]) == (
        "negative",
        "neutral",
        "",
    )

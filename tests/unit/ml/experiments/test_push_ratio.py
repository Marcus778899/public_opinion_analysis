from datetime import UTC, datetime

import pytest

from radar.common.enums import Polarity
from radar.ml.experiments.push_ratio import (
    PostVotes,
    RatioSummary,
    fetch_votes,
    push_ratio,
    render_report,
    spearman,
    summarize,
)
from tests.unit.ml.fakes import FakeClickHouse

POS, NEU, NEG = Polarity.POSITIVE, Polarity.NEUTRAL, Polarity.NEGATIVE


def votes(polarity: Polarity, push: int, boo: int, pid: str = "p") -> PostVotes:
    return PostVotes(pid, polarity, push, boo)


def test_push_ratio_basic():
    assert push_ratio(30, 10) == 0.75


@pytest.mark.parametrize(("push", "boo"), [(0, 0), (5, 4)])
def test_push_ratio_too_few_votes_returns_none(push, boo):
    assert push_ratio(push, boo) is None


def test_fetch_votes_converts_types():
    ch = FakeClickHouse(
        [{"post_id": "a", "polarity": "negative", "push_count": "3", "boo_count": 12}]
    )

    assert fetch_votes(ch, "groq:q", "prompt-v4") == [votes(NEG, 3, 12, "a")]
    assert ch.queries[0][1] == {"labeler": "groq:q", "version": "prompt-v4"}


def test_summarize_groups_by_polarity_and_skips_low_votes():
    rows = [
        votes(POS, 90, 10),
        votes(POS, 70, 30),
        votes(POS, 80, 20),
        votes(NEG, 2, 18),
        votes(NEG, 1, 1),  # 票數不足，略過
        votes(NEU, 1, 1),  # 整個類別都略過
    ]

    summaries = {s.polarity: s for s in summarize(rows)}

    assert set(summaries) == {POS, NEG}
    assert (summaries[POS].n, summaries[POS].median) == (3, 0.8)
    assert (summaries[POS].p25, summaries[POS].p75) == pytest.approx((0.75, 0.85))
    assert summaries[NEG] == RatioSummary(NEG, 1, 0.1, 0.1, 0.1)


def test_spearman_positive_when_sentiment_tracks_ratio():
    rows = [votes(NEG, 1, 19), votes(NEU, 10, 10), votes(POS, 19, 1), votes(POS, 18, 2)]

    assert spearman(rows) > 0.9


def test_spearman_insufficient_or_constant_returns_none():
    assert spearman([votes(POS, 10, 0)]) is None
    assert spearman([votes(POS, 10, 0), votes(POS, 9, 1), votes(POS, 8, 2)]) is None


def test_render_report_contains_each_polarity():
    summaries = [RatioSummary(POS, 3, 0.8, 0.75, 0.85), RatioSummary(NEG, 1, 0.1, 0.1, 0.1)]
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)

    report = render_report(summaries, 0.42, "groq:q", "prompt-v4", now)

    assert "| positive | 3 | 0.80 | 0.75 | 0.85 |" in report
    assert "| negative | 1 | 0.10 |" in report
    assert "0.420" in report and "`groq:q`" in report
    assert "## 結論" in report


def test_render_report_without_correlation():
    report = render_report([], None, "x", "v", datetime(2026, 10, 7, tzinfo=UTC))

    assert "資料不足" in report

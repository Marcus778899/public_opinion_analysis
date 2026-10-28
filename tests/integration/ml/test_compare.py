"""compare 在空表與特殊字元版本名上的行為（完整指標見 acceptance/bert-compare）。"""

from datetime import UTC, datetime

from radar.common.settings import InferenceRole
from radar.ml.training import compare

SINCE = datetime(2026, 10, 10, tzinfo=UTC)


def test_fetch_pairs_on_empty_tables_returns_empty(clickhouse):
    assert compare.fetch_pairs(clickhouse, "a", "b", SINCE, "l", "v") == []


def test_fetch_pairs_version_with_quote_is_treated_as_value(clickhouse):
    assert compare.fetch_pairs(clickhouse, "a' OR '1'='1", "b", SINCE, "l", "v") == []


def test_fetch_latency_on_empty_tables_returns_zero_posts(clickhouse):
    stats = compare.fetch_latency(clickhouse, "v", InferenceRole.SHADOW, SINCE)

    assert stats.n == 0

"""shadow 的快取只從 predictions_shadow 載入（開發規格 7.27），在真的 ClickHouse 上。"""

import pytest

from radar.ml.inference.main import HashCache, load_cache

MV = "bert-it-1"
H_SHADOW, H_PRIMARY = "1" * 64, "2" * 64


def insert(ch, table: str, post_id: str, digest: str) -> None:
    ch.execute(
        f"INSERT INTO {table} (post_id, model_version, predicted_at, polarity, scores, text_hash) "
        f"VALUES ('{post_id}', '{MV}', '2026-10-16 01:00:00', 'neutral', map('neutral', 1.0), "
        f"'{digest}')"
    )


@pytest.fixture
def tables(clickhouse):
    clickhouse.execute("TRUNCATE TABLE predictions")
    clickhouse.execute("TRUNCATE TABLE predictions_shadow")
    return clickhouse


def test_load_cache_shadow_table_ignores_primary_rows(tables):
    insert(tables, "predictions_shadow", "Stock.M.1.A.111", H_SHADOW)
    insert(tables, "predictions", "Stock.M.2.A.222", H_PRIMARY)
    cache = HashCache(10)

    loaded = load_cache(tables, MV, cache, "predictions_shadow")

    assert loaded == 1
    assert cache.get("Stock.M.1.A.111") == H_SHADOW
    assert cache.get("Stock.M.2.A.222") is None


def test_load_cache_default_table_ignores_shadow_rows(tables):
    insert(tables, "predictions_shadow", "Stock.M.1.A.111", H_SHADOW)
    insert(tables, "predictions", "Stock.M.2.A.222", H_PRIMARY)
    cache = HashCache(10)

    load_cache(tables, MV, cache)

    assert cache.get("Stock.M.2.A.222") == H_PRIMARY
    assert cache.get("Stock.M.1.A.111") is None

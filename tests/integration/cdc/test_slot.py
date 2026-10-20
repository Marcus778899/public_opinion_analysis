"""read_slot 對真實 PG 的查詢；需要 wal_level=logical 的容器才能建立 replication slot。"""

import pytest
from sqlalchemy import Engine, create_engine, text

from radar.cdc.watchdog import read_slot

SLOT = "watchdog_test"


@pytest.fixture(scope="module")
def logical_pg(postgres_url):
    # NOTE: compose 的 postgres 服務已設 wal_level=logical
    engine = create_engine(postgres_url)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t"))
    engine.dispose()


@pytest.fixture
def slot(logical_pg: Engine):
    # NOTE: test_decoding 是 PG 內建的 output plugin，不需要 publication
    with logical_pg.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS t (id serial PRIMARY KEY, v text)"))
    # NOTE: 建立 logical slot 的 transaction 不可先有寫入，所以和建表分開
    with logical_pg.begin() as conn:
        conn.execute(
            text("SELECT pg_create_logical_replication_slot(:s, 'test_decoding')"), {"s": SLOT}
        )
    yield SLOT
    with logical_pg.begin() as conn:
        conn.execute(text("SELECT pg_drop_replication_slot(:s)"), {"s": SLOT})


def write_rows(engine: Engine, n: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO t (v) SELECT repeat('x', 1000) FROM generate_series(1, :n)"),
            {"n": n},
        )


def test_read_slot_missing_returns_none(logical_pg):
    with logical_pg.connect() as conn:
        assert read_slot(conn, "no_such_slot") is None


def test_read_slot_unconsumed_slot_is_inactive_and_lag_grows_with_writes(logical_pg, slot):
    with logical_pg.connect() as conn:
        before = read_slot(conn, slot)
    write_rows(logical_pg, 500)
    with logical_pg.connect() as conn:
        after = read_slot(conn, slot)

    assert before is not None and after is not None
    assert not after.active
    assert after.lag_bytes > before.lag_bytes + 500 * 1000


def test_read_slot_after_consuming_changes_lag_drops(logical_pg, slot):
    write_rows(logical_pg, 500)
    with logical_pg.connect() as conn:
        lagging = read_slot(conn, slot)
    with logical_pg.begin() as conn:
        conn.execute(
            text("SELECT count(*) FROM pg_logical_slot_get_changes(:s, NULL, NULL)"), {"s": slot}
        )
    with logical_pg.connect() as conn:
        consumed = read_slot(conn, slot)

    assert lagging is not None and consumed is not None
    assert consumed.lag_bytes < lagging.lag_bytes
    assert consumed.lag_bytes < 100_000

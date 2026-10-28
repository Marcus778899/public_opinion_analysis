"""read_slot 對真實 PG 的查詢；需要 wal_level=logical 的容器才能建立 replication slot。"""

import pytest
from sqlalchemy import Connection, Engine, create_engine, text

from radar.cdc.watchdog import read_slot


@pytest.fixture(scope="module")
def logical_pg(postgres_url):
    # NOTE: compose 的 postgres 服務已設 wal_level=logical
    engine = create_engine(postgres_url)
    yield engine
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t"))
    engine.dispose()


@pytest.fixture
def slot(logical_pg: Engine, worker: str):
    # NOTE: replication slot 是整個 cluster 共用的，名稱帶 worker 才不會互撞
    name = f"watchdog_test_{worker}"
    # NOTE: test_decoding 是 PG 內建的 output plugin，不需要 publication
    with logical_pg.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS t (id serial PRIMARY KEY, v text)"))
    # NOTE: 建立 logical slot 的 transaction 不可先有寫入，所以和建表分開
    with logical_pg.begin() as conn:
        conn.execute(
            text("SELECT pg_create_logical_replication_slot(:s, 'test_decoding')"), {"s": name}
        )
    yield name
    with logical_pg.begin() as conn:
        conn.execute(text("SELECT pg_drop_replication_slot(:s)"), {"s": name})


def write_rows(engine: Engine, n: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO t (v) SELECT repeat('x', 1000) FROM generate_series(1, :n)"),
            {"n": n},
        )


def confirmed_flush_lsn(engine: Engine, slot: str) -> int:
    """slot 已確認的 WAL 位置（相對 0/0 的 byte 數）；只受自己 slot 的消費影響。"""
    with engine.connect() as conn:
        return int(
            conn.execute(
                text(
                    "SELECT pg_wal_lsn_diff(confirmed_flush_lsn, '0/0') "
                    "FROM pg_replication_slots WHERE slot_name = :s"
                ),
                {"s": slot},
            ).scalar_one()
        )


def current_wal(conn: Connection) -> int:
    return int(
        conn.execute(text("SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), '0/0')")).scalar_one()
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


def test_read_slot_after_consuming_changes_lag_measured_from_confirmed_flush(logical_pg, slot):
    write_rows(logical_pg, 500)
    with logical_pg.connect() as conn:
        lagging = read_slot(conn, slot)
    flushed_before = confirmed_flush_lsn(logical_pg, slot)
    with logical_pg.begin() as conn:
        conn.execute(
            text("SELECT count(*) FROM pg_logical_slot_get_changes(:s, NULL, NULL)"), {"s": slot}
        )
    with logical_pg.connect() as conn:
        wal_before = current_wal(conn)
        consumed = read_slot(conn, slot)
        wal_after = current_wal(conn)
    flushed_after = confirmed_flush_lsn(logical_pg, slot)

    assert lagging is not None and consumed is not None
    # NOTE: lag 含整個 cluster 的 WAL，平行時別的 worker 也在寫（#117），
    # NOTE: 所以斷言自己 slot 的 confirmed_flush_lsn 前進量，不比 lag 的絕對值
    assert flushed_after - flushed_before > 400_000
    # NOTE: 其他 worker 的寫入只會同時推高上下界，lag 仍夾在自己 slot 的位置之間
    assert wal_before - flushed_after <= consumed.lag_bytes <= wal_after - flushed_after
    assert consumed.active is False

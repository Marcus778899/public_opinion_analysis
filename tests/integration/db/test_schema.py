from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from radar.common.db.session import make_engine

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
POST_ID = "Stock.M.1759730000.A.1B2"


@pytest.fixture
def alembic_cfg(postgres_env) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    return cfg


@pytest.fixture
def engine(postgres_env, alembic_cfg) -> Engine:
    eng = make_engine(postgres_env)
    yield eng
    eng.dispose()


def insert_post(conn, post_id=POST_ID):
    conn.execute(
        text(
            "INSERT INTO posts (post_id, board, url, created_at, crawled_at) "
            "VALUES (:id, 'Stock', 'u', :now, :now)"
        ),
        {"id": post_id, "now": NOW},
    )


def run_and_rollback(engine, fn):
    """在 transaction 中執行後一律 rollback，避免測試間互相污染資料。"""
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            return fn(conn)
        finally:
            trans.rollback()


def test_models_and_migrations_are_in_sync(alembic_cfg):
    command.check(alembic_cfg)


def test_downgrade_then_upgrade_succeeds(alembic_cfg):
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")


def test_boards_interval_below_30_rejected(engine):
    def fn(conn):
        conn.execute(text("INSERT INTO boards (board, interval_sec) VALUES ('Stock', 10)"))

    with pytest.raises(IntegrityError, match="ck_boards_interval_sec_min"):
        run_and_rollback(engine, fn)


def test_comment_type_outside_enum_rejected(engine):
    def fn(conn):
        insert_post(conn)
        conn.execute(
            text("INSERT INTO comments (post_id, floor, type) VALUES (:id, 1, 'like')"),
            {"id": POST_ID},
        )

    with pytest.raises(IntegrityError, match="ck_comments_comment_type"):
        run_and_rollback(engine, fn)


def test_comment_requires_existing_post(engine):
    def fn(conn):
        conn.execute(text("INSERT INTO comments (post_id, floor, type) VALUES ('nope', 1, 'push')"))

    with pytest.raises(IntegrityError, match="fk_comments_post_id_posts"):
        run_and_rollback(engine, fn)


def test_post_defaults_applied_by_database(engine):
    def fn(conn):
        insert_post(conn)
        return conn.execute(
            text("SELECT push_count, boo_count, is_deleted FROM posts WHERE post_id = :id"),
            {"id": POST_ID},
        ).one()

    assert tuple(run_and_rollback(engine, fn)) == (0, 0, False)


def test_board_defaults_applied_by_database(engine):
    def fn(conn):
        conn.execute(text("INSERT INTO boards (board, interval_sec) VALUES ('Stock', 60)"))
        return conn.execute(text("SELECT enabled, recrawl_min_push, updated_at FROM boards")).one()

    enabled, recrawl_min_push, updated_at = run_and_rollback(engine, fn)
    assert (enabled, recrawl_min_push) == (True, 0)
    assert updated_at is not None


def test_table_comments_record_writer(engine):
    def fn(conn):
        rows = conn.execute(
            text(
                "SELECT c.relname, obj_description(c.oid) FROM pg_class c "
                "WHERE c.relname IN ('posts', 'comments', 'boards', 'crawl_state')"
            )
        )
        return dict(rows.all())

    comments = run_and_rollback(engine, fn)
    assert comments == {
        "posts": "writer: ingest; debezium: yes",
        "comments": "writer: ingest; debezium: yes",
        "boards": "writer: api; debezium: no",
        "crawl_state": "writer: scheduler; debezium: no",
    }

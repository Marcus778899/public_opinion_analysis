from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from radar.collector.scheduler import latest_post_since
from radar.common.db.session import make_engine

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
T0 = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
FAR_FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


@pytest.fixture
def engine(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    eng = make_engine(postgres_env)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE boards, crawl_state, comments, posts CASCADE"))
        conn.execute(
            text(
                "INSERT INTO boards (board, interval_sec, recrawl_min_push, enabled) "
                "VALUES ('Stock', 60, 0, true)"
            )
        )
    yield eng
    eng.dispose()


def add_post(engine, epoch: int, created_at: datetime) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO posts (post_id, board, url, created_at, crawled_at, push_count, "
                "boo_count, comment_count, is_deleted) "
                "VALUES (:id, 'Stock', 'u', :c, :c, 0, 0, 0, false)"
            ),
            {"id": f"Stock.M.{epoch}.A.001", "c": created_at},
        )


def test_latest_post_since_uses_filename_epoch_not_created_at(engine):
    add_post(engine, int(T0.timestamp()), FAR_FUTURE)

    since = latest_post_since(engine, "Stock", now=T0 + timedelta(hours=1))

    assert since == T0 - timedelta(minutes=10)


def test_latest_post_since_future_filename_clamped_to_now(engine):
    add_post(engine, int(FAR_FUTURE.timestamp()), T0)

    assert latest_post_since(engine, "Stock", now=T0) == T0 - timedelta(minutes=10)


def test_latest_post_since_no_posts_is_none(engine):
    assert latest_post_since(engine, "Stock", now=T0) is None

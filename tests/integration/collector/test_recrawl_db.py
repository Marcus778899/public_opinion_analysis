from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from radar.collector.recrawl import find_due_posts, record_dispatch
from radar.collector.scheduler import AdvisoryLock
from radar.common.db.session import make_engine, make_session_factory

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    eng = make_engine(postgres_env)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE boards, crawl_state, comments, posts CASCADE"))
        conn.execute(
            text(
                "INSERT INTO boards (board, interval_sec, recrawl_min_push, enabled) VALUES "
                "('Stock', 120, 0, true), ('Gossiping', 60, 10, true), ('Off', 60, 0, false)"
            )
        )
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    return make_session_factory(engine)


def add_post(engine, post_id, *, age, push=0, deleted=False, next_crawl=None):
    board = post_id.split(".", 1)[0]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO posts (post_id, board, url, created_at, crawled_at, push_count, "
                "is_deleted) VALUES (:id, :board, :url, :created, :created, :push, :deleted)"
            ),
            {
                "id": post_id,
                "board": board,
                "url": f"https://www.ptt.cc/bbs/{board}/{post_id.split('.', 1)[1]}.html",
                "created": NOW - age,
                "push": push,
                "deleted": deleted,
            },
        )
        if next_crawl is not None:
            conn.execute(
                text(
                    "INSERT INTO crawl_state (post_id, next_crawl_at, last_dispatched) "
                    "VALUES (:id, :next, :next)"
                ),
                {"id": post_id, "next": next_crawl},
            )


def due_ids(session_factory, limit=100):
    with session_factory() as session:
        return [p.post_id for p in find_due_posts(session, NOW, limit=limit)]


def test_due_posts_include_new_posts_without_state(engine, session_factory):
    add_post(engine, "Stock.M.1.A.001", age=timedelta(minutes=5))

    assert due_ids(session_factory) == ["Stock.M.1.A.001"]


def test_due_posts_exclude_not_yet_due(engine, session_factory):
    add_post(
        engine, "Stock.M.1.A.001", age=timedelta(minutes=5), next_crawl=NOW + timedelta(minutes=1)
    )
    add_post(
        engine, "Stock.M.2.A.002", age=timedelta(minutes=5), next_crawl=NOW - timedelta(seconds=1)
    )

    assert due_ids(session_factory) == ["Stock.M.2.A.002"]


def test_due_posts_exclude_older_than_24h(engine, session_factory):
    add_post(engine, "Stock.M.1.A.001", age=timedelta(hours=25))

    assert due_ids(session_factory) == []


def test_due_posts_exclude_deleted(engine, session_factory):
    add_post(engine, "Stock.M.1.A.001", age=timedelta(minutes=5), deleted=True)

    assert due_ids(session_factory) == []


def test_due_posts_apply_threshold_after_1h(engine, session_factory):
    add_post(engine, "Gossiping.M.1.A.001", age=timedelta(minutes=30), push=0)  # 1 小時內不看門檻
    add_post(engine, "Gossiping.M.2.A.002", age=timedelta(hours=2), push=3)  # 未達門檻 10
    add_post(engine, "Gossiping.M.3.A.003", age=timedelta(hours=2), push=10)

    assert sorted(due_ids(session_factory)) == ["Gossiping.M.1.A.001", "Gossiping.M.3.A.003"]


def test_due_posts_exclude_disabled_boards(engine, session_factory):
    add_post(engine, "Off.M.1.A.001", age=timedelta(minutes=5))

    assert due_ids(session_factory) == []


def test_due_posts_never_dispatched_first_and_limited(engine, session_factory):
    add_post(
        engine, "Stock.M.1.A.001", age=timedelta(minutes=5), next_crawl=NOW - timedelta(minutes=1)
    )
    add_post(engine, "Stock.M.2.A.002", age=timedelta(minutes=5))

    assert due_ids(session_factory, limit=1) == ["Stock.M.2.A.002"]


def test_record_dispatch_upserts_crawl_state(engine, session_factory):
    add_post(engine, "Stock.M.1.A.001", age=timedelta(minutes=5))
    add_post(engine, "Stock.M.2.A.002", age=timedelta(hours=23, minutes=59, seconds=59))
    with session_factory() as session:
        posts = find_due_posts(session, NOW, limit=10)
        record_dispatch(session, posts, NOW, time_scale=1.0)
        record_dispatch(session, posts, NOW, time_scale=1.0)  # 重複寫入不報錯
        session.commit()

    with engine.connect() as conn:
        rows = dict(conn.execute(text("SELECT post_id, next_crawl_at FROM crawl_state")).all())
    assert rows["Stock.M.1.A.001"] == NOW + timedelta(minutes=2)
    assert rows["Stock.M.2.A.002"] == NOW + timedelta(hours=1)
    assert due_ids(session_factory) == []


def test_advisory_lock_only_one_holder(engine):
    first, second = AdvisoryLock(engine, key=424242), AdvisoryLock(engine, key=424242)
    try:
        assert first.try_acquire()
        assert first.is_held()
        assert not second.try_acquire()
        assert not second.is_held()
    finally:
        first.release()
        second.release()


def test_advisory_lock_released_when_holder_releases_or_disconnects(engine):
    first, second = AdvisoryLock(engine, key=434343), AdvisoryLock(engine, key=434343)
    try:
        assert first.try_acquire()
        first.release()
        assert second.try_acquire()
        second._conn.invalidate()  # 模擬連線中斷
        second._conn = None
        assert first.try_acquire()
    finally:
        first.release()
        second.release()


def test_advisory_lock_wait_gives_up_when_stopped(engine):
    holder, waiter = AdvisoryLock(engine, key=454545), AdvisoryLock(engine, key=454545)
    try:
        assert holder.try_acquire()
        assert waiter.wait_until_acquired(poll_s=0.01, stop=lambda: True) is False
    finally:
        holder.release()
        waiter.release()

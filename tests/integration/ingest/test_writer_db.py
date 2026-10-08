from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from radar.common.db.session import make_engine, make_session_factory
from radar.ingest import writer
from radar.ingest.writer import write_batch
from tests.helpers.raw_posts import T0, make_post

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
POST_ID = "Stock.M.1791345103.A.E41"


@pytest.fixture
def session_factory(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    engine = make_engine(postgres_env)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE boards, crawl_state, comments, posts CASCADE"))
    yield make_session_factory(engine)
    engine.dispose()


def write(session_factory, posts):
    with session_factory() as session:
        stats = write_batch(session, posts)
        session.commit()
    return stats


def query(session_factory, sql, **params):
    with session_factory() as session:
        return session.execute(text(sql), params).all()


def post_row(session_factory, post_id=POST_ID):
    [row] = query(
        session_factory,
        "SELECT push_count, boo_count, title, content, crawled_at, is_deleted, xmin::text "
        "FROM posts WHERE post_id = :id",
        id=post_id,
    )
    return row


def test_new_post_and_comments_inserted(session_factory):
    stats = write(session_factory, [make_post(n_push=2, n_boo=1, n_arrow=1)])

    assert (stats.posts_written, stats.comments_inserted) == (1, 4)
    row = post_row(session_factory)
    assert (row.push_count, row.boo_count, row.is_deleted) == (2, 1, False)
    types = [r[0] for r in query(session_factory, "SELECT type FROM comments ORDER BY floor")]
    assert types == ["push", "push", "boo", "arrow"]


def test_replaying_same_batch_writes_nothing(session_factory):
    batch = [make_post(n_push=2)]
    write(session_factory, batch)
    version = post_row(session_factory).xmin

    stats = write(session_factory, batch)

    assert (stats.posts_written, stats.comments_inserted) == (0, 0)
    assert post_row(session_factory).xmin == version  # 沒有實際更新，就不會有 CDC 事件


def test_older_snapshot_does_not_overwrite_newer(session_factory):
    write(session_factory, [make_post(crawled_at=T0 + timedelta(minutes=5), n_push=5)])

    stats = write(session_factory, [make_post(crawled_at=T0, n_push=1)])

    assert stats.posts_written == 0
    assert post_row(session_factory).push_count == 5


def test_newer_snapshot_with_changes_updates_post(session_factory):
    write(session_factory, [make_post(n_push=1)])
    later = T0 + timedelta(minutes=2)

    stats = write(session_factory, [make_post(crawled_at=later, n_push=3, title="[新聞] 改標題")])

    assert stats.posts_written == 1
    row = post_row(session_factory)
    assert (row.push_count, row.title, row.crawled_at) == (3, "[新聞] 改標題", later)


def test_newer_snapshot_without_changes_does_not_write(session_factory):
    write(session_factory, [make_post(n_push=1)])
    version = post_row(session_factory).xmin

    stats = write(session_factory, [make_post(crawled_at=T0 + timedelta(minutes=2), n_push=1)])

    assert stats.posts_written == 0
    row = post_row(session_factory)
    assert row.crawled_at == T0  # crawled_at 不算變化，也不會被單獨更新
    assert row.xmin == version


def test_new_comments_appended_existing_kept(session_factory):
    write(session_factory, [make_post(n_push=2)])

    stats = write(session_factory, [make_post(crawled_at=T0 + timedelta(minutes=2), n_push=5)])

    assert stats.comments_inserted == 3
    assert query(session_factory, "SELECT count(*) FROM comments")[0][0] == 5


def test_duplicate_post_in_same_batch_does_not_error(session_factory):
    batch = [
        make_post(crawled_at=T0, n_push=1),
        make_post(crawled_at=T0 + timedelta(minutes=1), n_push=4),
    ]

    stats = write(session_factory, batch)

    assert (stats.received, stats.posts_written) == (2, 1)
    assert post_row(session_factory).push_count == 4


def test_deleted_post_only_sets_flag(session_factory):
    write(session_factory, [make_post(n_push=3, content="原本的內文")])

    stats = write(
        session_factory, [make_post(crawled_at=T0 + timedelta(minutes=5), is_deleted=True)]
    )

    assert stats.marked_deleted == 1
    row = post_row(session_factory)
    assert (row.is_deleted, row.push_count, row.content) == (True, 3, "原本的內文")
    assert (
        write(
            session_factory, [make_post(crawled_at=T0 + timedelta(minutes=9), is_deleted=True)]
        ).marked_deleted
        == 0
    )


def test_deleted_unknown_post_is_ignored(session_factory):
    stats = write(session_factory, [make_post(is_deleted=True)])

    assert stats.marked_deleted == 0
    assert query(session_factory, "SELECT count(*) FROM posts")[0][0] == 0


def test_large_comment_batch_is_chunked(session_factory, monkeypatch):
    monkeypatch.setattr(writer, "COMMENT_CHUNK_SIZE", 7)

    stats = write(session_factory, [make_post(n_push=10, n_boo=6)])

    assert stats.comments_inserted == 16
    assert query(session_factory, "SELECT count(*) FROM comments")[0][0] == 16

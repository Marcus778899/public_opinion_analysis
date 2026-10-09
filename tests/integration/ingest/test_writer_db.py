from datetime import timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DataError

from radar.common.db.session import make_engine, make_session_factory
from radar.ingest import writer
from radar.ingest.main import IngestHandler
from radar.ingest.writer import write_batch, write_each
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
    assert row.crawled_at == T0 + timedelta(minutes=5)
    assert (
        write(
            session_factory, [make_post(crawled_at=T0 + timedelta(minutes=9), is_deleted=True)]
        ).marked_deleted
        == 0
    )


# ---------- 撤銷刪除（開發規格 7.14） ----------
DELETED_AT = T0 + timedelta(minutes=5)


def write_then_delete(session_factory):
    write(session_factory, [make_post(n_push=3, content="原本的內文")])
    write(session_factory, [make_post(crawled_at=DELETED_AT, is_deleted=True)])


def test_deleted_snapshot_updates_crawled_at(session_factory):
    write_then_delete(session_factory)

    row = post_row(session_factory)
    assert (row.is_deleted, row.crawled_at) == (True, DELETED_AT)


def test_older_deleted_snapshot_does_not_mark_newer_post(session_factory):
    write(session_factory, [make_post(crawled_at=T0 + timedelta(minutes=5), n_push=2)])

    stats = write(session_factory, [make_post(crawled_at=T0, is_deleted=True)])

    assert stats.marked_deleted == 0
    assert post_row(session_factory).is_deleted is False


def test_newer_live_snapshot_undeletes_post_with_new_content(session_factory):
    write_then_delete(session_factory)
    later = DELETED_AT + timedelta(minutes=1)

    stats = write(session_factory, [make_post(crawled_at=later, n_push=4, content="新內文")])

    assert stats.posts_written == 1
    row = post_row(session_factory)
    assert (row.is_deleted, row.push_count, row.content, row.crawled_at) == (
        False,
        4,
        "新內文",
        later,
    )


def test_newer_live_snapshot_without_changes_still_undeletes(session_factory):
    write_then_delete(session_factory)

    stats = write(
        session_factory,
        [make_post(crawled_at=DELETED_AT + timedelta(minutes=1), n_push=3, content="原本的內文")],
    )

    assert stats.posts_written == 1
    assert post_row(session_factory).is_deleted is False


def test_live_snapshot_older_than_deletion_does_not_undelete(session_factory):
    write_then_delete(session_factory)

    stats = write(
        session_factory, [make_post(crawled_at=DELETED_AT - timedelta(minutes=1), n_push=9)]
    )

    assert stats.posts_written == 0
    row = post_row(session_factory)
    assert (row.is_deleted, row.push_count) == (True, 3)


def test_live_post_not_deleted_newer_snapshot_without_changes_still_skipped(session_factory):
    write(session_factory, [make_post(n_push=2)])
    version = post_row(session_factory).xmin

    stats = write(session_factory, [make_post(crawled_at=T0 + timedelta(minutes=1), n_push=2)])

    assert stats.posts_written == 0
    assert post_row(session_factory).xmin == version


def test_delete_then_undelete_in_same_batch_keeps_latest(session_factory):
    write(session_factory, [make_post(n_push=1)])
    batch = [
        make_post(crawled_at=DELETED_AT, is_deleted=True),
        make_post(crawled_at=DELETED_AT + timedelta(minutes=1), n_push=2),
    ]

    stats = write(session_factory, batch)

    assert (stats.posts_written, stats.marked_deleted) == (1, 0)
    row = post_row(session_factory)
    assert (row.is_deleted, row.push_count) == (False, 2)


def test_deleted_unknown_post_is_ignored(session_factory):
    stats = write(session_factory, [make_post(is_deleted=True)])

    assert stats.marked_deleted == 0
    assert query(session_factory, "SELECT count(*) FROM posts")[0][0] == 0


def test_large_comment_batch_is_chunked(session_factory, monkeypatch):
    monkeypatch.setattr(writer, "COMMENT_CHUNK_SIZE", 7)

    stats = write(session_factory, [make_post(n_push=10, n_boo=6)])

    assert stats.comments_inserted == 16
    assert query(session_factory, "SELECT count(*) FROM comments")[0][0] == 16


# ---------- 逐筆模式（開發規格 7.13） ----------
OTHER_ID = "Stock.M.1791345200.A.001"
POISON_ID = "Stock.M.1791345300.A.002"


def write_each_committed(session_factory, posts):
    with session_factory() as session:
        result = write_each(session, posts)
        session.commit()
    return result


def post_ids(session_factory):
    return [r[0] for r in query(session_factory, "SELECT post_id FROM posts ORDER BY post_id")]


def test_write_each_rejects_nul_byte_post_and_writes_others(session_factory):
    batch = [make_post(), make_post(POISON_ID, content="a\x00b"), make_post(OTHER_ID)]

    stats, rejections = write_each_committed(session_factory, batch)

    assert [r.index for r in rejections] == [1]
    assert isinstance(rejections[0].error, DataError)
    assert post_ids(session_factory) == sorted([POST_ID, OTHER_ID])
    assert stats.posts_written == 2


def test_write_each_rejection_index_points_to_original_position(session_factory):
    batch = [make_post(), make_post(OTHER_ID), make_post(POISON_ID, title="x\x00")]

    _, rejections = write_each_committed(session_factory, batch)

    assert [r.index for r in rejections] == [2]


def test_write_each_duplicates_write_latest_once(session_factory):
    batch = [make_post(n_push=1), make_post(crawled_at=T0 + timedelta(minutes=1), n_push=3)]

    stats, rejections = write_each_committed(session_factory, batch)

    assert rejections == []
    assert stats.posts_written == 1
    assert post_row(session_factory).push_count == 3


def test_write_each_all_valid_matches_write_batch_stats(session_factory, postgres_env):
    batch = [make_post(n_push=2), make_post(OTHER_ID, n_boo=1)]

    each_stats, _ = write_each_committed(session_factory, batch)
    with make_engine(postgres_env).begin() as conn:
        conn.execute(text("TRUNCATE comments, posts CASCADE"))
    batch_stats = write(session_factory, batch)

    assert each_stats == batch_stats


def test_ingest_handler_batch_with_poison_post_commits_rest(session_factory):
    batch = [make_post(), make_post(POISON_ID, content="\x00"), make_post(OTHER_ID)]

    rejections = IngestHandler(session_factory)(batch)

    assert [r.index for r in rejections] == [1]
    assert post_ids(session_factory) == sorted([POST_ID, OTHER_ID])

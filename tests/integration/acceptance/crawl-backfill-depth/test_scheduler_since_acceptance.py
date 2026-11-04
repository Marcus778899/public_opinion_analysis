"""開發規格 7.28 A：Scheduler 送列表任務前查 PG，since ＝ 該看板最新 created_at 減 10 分鐘。"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from tests.unit.common.kafka.fakes import FakeProducer

from radar.collector.scheduler import make_list_task_sender
from radar.common.db.session import make_engine
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings

ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"
T0 = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)


@pytest.fixture
def engine(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    eng = make_engine(postgres_env)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE boards, crawl_state, comments, posts CASCADE"))
        conn.execute(
            text(
                "INSERT INTO boards (board, interval_sec, recrawl_min_push, enabled) VALUES "
                "('Gossiping', 60, 10, true), ('HatePolitics', 60, 0, true), "
                "('Stock', 120, 0, true)"
            )
        )
    yield eng
    eng.dispose()


def add_post(engine, post_id: str, created_at: datetime, *, deleted: bool = False) -> None:
    board = post_id.split(".", 1)[0]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO posts (post_id, board, url, created_at, crawled_at, push_count, "
                "boo_count, comment_count, is_deleted) "
                "VALUES (:id, :board, :url, :c, :c, 0, 0, 0, :d)"
            ),
            {
                "id": post_id,
                "board": board,
                "url": f"https://www.ptt.cc/bbs/{board}/{post_id.split('.', 1)[1]}.html",
                "c": created_at,
                "d": deleted,
            },
        )


def sender_for(engine):
    fake = FakeProducer()
    producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake)
    return make_list_task_sender(producer, lambda: [], engine=engine), fake


def sent_tasks(fake: FakeProducer) -> list[dict]:
    return [json.loads(m["value"]) for m in fake.produced if m["topic"] == names.CRAWL_TASKS]


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_since_is_latest_created_at_minus_ten_minutes(engine):
    add_post(engine, "Gossiping.M.1.A.001", T0 - timedelta(hours=5))
    add_post(engine, "Gossiping.M.2.A.002", T0)
    add_post(engine, "Gossiping.M.3.A.003", T0 - timedelta(hours=1))
    send, fake = sender_for(engine)

    send("Gossiping")

    [task] = sent_tasks(fake)
    assert parse(task["since"]) == T0 - timedelta(minutes=10)
    assert task["reason"] == "schedule"
    assert task["type"] == "list"
    assert task["backfill_depth"] == 0


def test_since_only_looks_at_the_same_board(engine):
    add_post(engine, "Gossiping.M.1.A.001", T0 - timedelta(hours=2))
    add_post(engine, "HatePolitics.M.2.A.002", T0)
    send, fake = sender_for(engine)

    send("Gossiping")
    send("HatePolitics")

    first, second = sent_tasks(fake)
    assert parse(first["since"]) == T0 - timedelta(hours=2, minutes=10)
    assert parse(second["since"]) == T0 - timedelta(minutes=10)


def test_since_is_null_when_board_has_no_posts(engine):
    add_post(engine, "Gossiping.M.1.A.001", T0)
    send, fake = sender_for(engine)

    send("Stock")

    [task] = sent_tasks(fake)
    assert task["since"] is None
    assert task["board"] == "Stock"


def test_since_follows_newest_post_on_every_dispatch(engine):
    add_post(engine, "Gossiping.M.1.A.001", T0 - timedelta(hours=3))
    send, fake = sender_for(engine)
    send("Gossiping")
    add_post(engine, "Gossiping.M.2.A.002", T0)

    send("Gossiping")

    first, second = sent_tasks(fake)
    assert parse(first["since"]) == T0 - timedelta(hours=3, minutes=10)
    assert parse(second["since"]) == T0 - timedelta(minutes=10)


def test_deleted_post_still_counts_as_latest(engine):
    add_post(engine, "Gossiping.M.1.A.001", T0 - timedelta(hours=1))
    add_post(engine, "Gossiping.M.2.A.002", T0, deleted=True)
    send, fake = sender_for(engine)

    send("Gossiping")

    [task] = sent_tasks(fake)
    assert parse(task["since"]) == T0 - timedelta(minutes=10)


def test_pg_failure_sends_task_with_null_since(engine):
    dead = create_engine("postgresql+psycopg://radar@127.0.0.1:1/none")
    send, fake = sender_for(dead)

    send("Gossiping")  # 不拋例外，任務照送

    [task] = sent_tasks(fake)
    assert task["since"] is None
    assert task["reason"] == "schedule"
    assert fake._pending == []
    dead.dispose()


def test_sender_without_engine_still_sends_null_since():
    fake = FakeProducer()
    send = make_list_task_sender(
        JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake), lambda: []
    )

    send("Gossiping")

    [task] = sent_tasks(fake)
    assert task["since"] is None

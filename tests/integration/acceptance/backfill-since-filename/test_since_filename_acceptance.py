"""開發規格 7.30 E：since 取檔名 epoch 最大值減 10 分鐘，不受標頭時間影響。"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from tests.unit.common.kafka.fakes import FakeProducer

from radar.collector import scheduler
from radar.collector.scheduler import make_list_task_sender
from radar.common.db.session import make_engine
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings

ALEMBIC_INI = Path(__file__).resolve().parents[4] / "alembic.ini"
T0 = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
FAR_FUTURE = datetime(2099, 1, 1, tzinfo=UTC)


class FakeLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _record(self, level: str, msg: str, *args: object) -> None:
        self.records.append((level, msg % args if args else msg))

    def debug(self, msg: str, *args: object) -> None:
        self._record("DEBUG", msg, *args)

    def info(self, msg: str, *args: object) -> None:
        self._record("INFO", msg, *args)

    def warning(self, msg: str, *args: object) -> None:
        self._record("WARNING", msg, *args)

    def error(self, msg: str, *args: object) -> None:
        self._record("ERROR", msg, *args)

    def levels(self) -> list[str]:
        return [level for level, _ in self.records]


@pytest.fixture
def engine(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    eng = make_engine(postgres_env)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE boards, crawl_state, comments, posts CASCADE"))
        conn.execute(
            text(
                "INSERT INTO boards (board, interval_sec, recrawl_min_push, enabled) VALUES "
                "('Gossiping', 60, 10, true), ('Stock', 120, 0, true)"
            )
        )
    yield eng
    eng.dispose()


@pytest.fixture
def fake_log(monkeypatch) -> FakeLog:
    fake = FakeLog()
    monkeypatch.setattr(scheduler, "log", fake)
    return fake


def add_post(
    engine,
    board: str,
    file_epoch: int,
    created_at: datetime,
    *,
    seq: str = "001",
    deleted: bool = False,
) -> None:
    post_id = f"{board}.M.{file_epoch}.A.{seq}"
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
                "url": f"https://www.ptt.cc/bbs/{board}/M.{file_epoch}.A.{seq}.html",
                "c": created_at,
                "d": deleted,
            },
        )


def send_once(engine, board: str = "Gossiping") -> dict:
    fake = FakeProducer()
    producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake)
    make_list_task_sender(producer, lambda: [], engine=engine)(board)
    [task] = [json.loads(m["value"]) for m in fake.produced if m["topic"] == names.CRAWL_TASKS]
    return task


def parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def test_since_is_max_filename_epoch_minus_ten_minutes(engine):
    e0 = int(T0.timestamp())
    add_post(engine, "Gossiping", e0 - 5 * 3600, T0, seq="001")
    add_post(engine, "Gossiping", e0, T0, seq="002")
    add_post(engine, "Gossiping", e0 - 3600, T0, seq="003")

    task = send_once(engine)

    assert parse(task["since"]) == T0 - timedelta(minutes=10)


def test_since_ignores_created_at_in_2099(engine):
    e0 = int(T0.timestamp())
    add_post(engine, "Gossiping", e0, FAR_FUTURE)

    task = send_once(engine)

    assert parse(task["since"]) == T0 - timedelta(minutes=10)


def test_since_ignores_created_at_earlier_than_filename(engine):
    e0 = int(T0.timestamp())
    add_post(engine, "Gossiping", e0, T0 - timedelta(days=30))

    task = send_once(engine)

    assert parse(task["since"]) == T0 - timedelta(minutes=10)


def test_since_compares_epoch_numerically_not_as_text(engine):
    # 9 位數與 10 位數的 epoch：字串比較會選錯
    add_post(engine, "Gossiping", 999_999_999, T0, seq="001")
    add_post(engine, "Gossiping", 1_000_000_000, T0, seq="002")

    task = send_once(engine)

    assert parse(task["since"]) == datetime.fromtimestamp(1_000_000_000 - 600, UTC)


def test_deleted_post_filename_still_counts(engine):
    e0 = int(T0.timestamp())
    add_post(engine, "Gossiping", e0 - 3600, T0 - timedelta(hours=1), seq="001")
    add_post(engine, "Gossiping", e0, T0, seq="002", deleted=True)

    task = send_once(engine)

    assert parse(task["since"]) == T0 - timedelta(minutes=10)


def test_since_only_counts_same_board(engine):
    e0 = int(T0.timestamp())
    add_post(engine, "Gossiping", e0 - 7200, T0)
    add_post(engine, "Stock", e0, T0)

    task = send_once(engine)

    assert parse(task["since"]) == T0 - timedelta(hours=2, minutes=10)


def test_since_is_null_when_board_has_no_posts(engine):
    add_post(engine, "Gossiping", int(T0.timestamp()), T0)

    task = send_once(engine, "Stock")

    assert task["since"] is None


def test_filename_in_the_future_is_clamped_to_now_with_warning(engine, fake_log):
    add_post(engine, "Gossiping", int(FAR_FUTURE.timestamp()), T0)
    before = datetime.now(UTC)

    task = send_once(engine)

    after = datetime.now(UTC)
    since = parse(task["since"])
    assert before - timedelta(minutes=10) <= since <= after - timedelta(minutes=10)
    assert "WARNING" in fake_log.levels()

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from radar.api.deps import get_admin_consumer, get_producer, get_session
from radar.api.main import create_app
from radar.api.repository import BoardExistsError, BoardNotFoundError, BoardRepository
from radar.api.schemas import BoardCreate, BoardUpdate
from radar.common.db.session import make_engine, make_session_factory
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import ApiSettings, KafkaSettings
from tests.unit.api.conftest import FakeAdminConsumer
from tests.unit.common.kafka.fakes import FakeProducer

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


@pytest.fixture
def session_factory(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    engine = make_engine(postgres_env)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE boards, crawl_state, comments, posts CASCADE"))
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def repo(session_factory):
    with session_factory() as session:
        yield BoardRepository(session)


def insert_post(session_factory, board, post_id, *, created_at, crawled_at):
    with session_factory() as session:
        session.execute(
            text(
                "INSERT INTO posts (post_id, board, url, created_at, crawled_at) "
                "VALUES (:id, :board, 'u', :created, :crawled)"
            ),
            {"id": post_id, "board": board, "created": created_at, "crawled": crawled_at},
        )
        session.commit()


def test_create_then_list(repo):
    repo.create(BoardCreate(board="Tech_Job", interval_sec=600))
    repo.create(BoardCreate(board="Gossiping", interval_sec=60, recrawl_min_push=10))

    boards = repo.list_all()

    assert [b.board for b in boards] == ["Gossiping", "Tech_Job"]
    assert boards[0].recrawl_min_push == 10
    assert boards[0].updated_at is not None


def test_create_duplicate_raises_board_exists(repo):
    repo.create(BoardCreate(board="Stock", interval_sec=120))

    with pytest.raises(BoardExistsError):
        repo.create(BoardCreate(board="Stock", interval_sec=60))
    assert len(repo.list_all()) == 1


def test_update_changes_fields_and_refreshes_updated_at(repo):
    before = repo.create(BoardCreate(board="Stock", interval_sec=120)).updated_at
    time.sleep(0.01)

    updated = repo.update("Stock", BoardUpdate(enabled=False))

    assert (updated.enabled, updated.interval_sec) == (False, 120)
    assert updated.updated_at > before


def test_update_unknown_raises_not_found(repo):
    with pytest.raises(BoardNotFoundError):
        repo.update("Nope", BoardUpdate(enabled=False))


def test_statuses_include_boards_without_posts(repo):
    repo.create(BoardCreate(board="Stock", interval_sec=120))

    [status] = repo.statuses(now=NOW)

    assert (status.board, status.last_changed_at, status.post_count_24h) == ("Stock", None, 0)


def test_statuses_last_changed_and_24h_count(repo, session_factory):
    repo.create(BoardCreate(board="Stock", interval_sec=120))
    repo.create(BoardCreate(board="Gossiping", interval_sec=60))
    old = NOW - timedelta(days=2)
    insert_post(session_factory, "Stock", "Stock.M.1.A.001", created_at=old, crawled_at=NOW)
    recent = NOW - timedelta(hours=1)
    insert_post(session_factory, "Stock", "Stock.M.2.A.002", created_at=recent, crawled_at=recent)

    statuses = {s.board: s for s in repo.statuses(now=NOW)}

    assert statuses["Stock"].last_changed_at == NOW
    assert statuses["Stock"].post_count_24h == 1
    assert statuses["Gossiping"].post_count_24h == 0


def test_api_end_to_end_with_real_db(session_factory):
    app = create_app(settings=ApiSettings(), use_lifespan=False)
    producer = JsonProducer(KafkaSettings(bootstrap_servers="unused"), producer=FakeProducer())

    def real_session():
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = real_session
    app.dependency_overrides[get_producer] = lambda: producer
    app.dependency_overrides[get_admin_consumer] = lambda: FakeAdminConsumer({})
    client = TestClient(app)

    assert client.post("/boards", json={"board": "Stock", "interval_sec": 120}).status_code == 201
    assert client.post("/boards", json={"board": "Stock", "interval_sec": 120}).status_code == 409
    assert client.patch("/boards/Stock", json={"interval_sec": 300}).json()["interval_sec"] == 300
    assert client.post("/boards/Stock/crawl").status_code == 202
    assert client.get("/status").json()["boards"][0]["board"] == "Stock"

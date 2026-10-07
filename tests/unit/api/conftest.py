from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from radar.api.deps import get_admin_consumer, get_producer, get_repository
from radar.api.main import create_app
from radar.api.repository import BoardExistsError, BoardNotFoundError
from radar.api.schemas import BoardCreate, BoardStatus, BoardUpdate
from radar.common.db.models import Board
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import ApiSettings, KafkaSettings
from tests.unit.common.kafka.fakes import FakeProducer

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


class FakeRepository:
    """記憶體版 BoardRepository，只模擬 API 需要的行為。"""

    def __init__(self) -> None:
        self.boards: dict[str, Board] = {}
        self.status_rows: list[BoardStatus] = []

    def add(self, name: str, *, enabled: bool = True, interval_sec: int = 60) -> Board:
        board = Board(
            board=name,
            enabled=enabled,
            interval_sec=interval_sec,
            recrawl_min_push=0,
            updated_at=NOW,
        )
        self.boards[name] = board
        return board

    def list_all(self) -> list[Board]:
        return [self.boards[k] for k in sorted(self.boards)]

    def get(self, board: str) -> Board:
        if board not in self.boards:
            raise BoardNotFoundError(board)
        return self.boards[board]

    def create(self, data: BoardCreate) -> Board:
        if data.board in self.boards:
            raise BoardExistsError(data.board)
        board = self.add(data.board, enabled=data.enabled, interval_sec=data.interval_sec)
        board.recrawl_min_push = data.recrawl_min_push
        return board

    def update(self, board: str, data: BoardUpdate) -> Board:
        obj = self.get(board)
        for key, value in data.changes().items():
            setattr(obj, key, value)
        return obj

    def statuses(self) -> list[BoardStatus]:
        return self.status_rows


class FakeAdminConsumer:
    def __init__(self, dlq_watermarks=None, error: Exception | None = None) -> None:
        self.dlq_watermarks = dlq_watermarks or {}
        self.error = error

    def list_topics(self, topic, timeout):
        if self.error:
            raise self.error
        meta = type("Meta", (), {})()
        if self.dlq_watermarks:
            t = type("T", (), {"error": None, "partitions": dict.fromkeys(self.dlq_watermarks)})()
            meta.topics = {topic: t}
        else:
            meta.topics = {}
        return meta

    def get_watermark_offsets(self, tp, timeout, cached):
        return self.dlq_watermarks[tp.partition]


@pytest.fixture
def repo() -> FakeRepository:
    return FakeRepository()


@pytest.fixture
def fake_producer() -> FakeProducer:
    return FakeProducer()


@pytest.fixture
def admin_consumer() -> FakeAdminConsumer:
    return FakeAdminConsumer({0: (0, 3), 1: (2, 4)})


@pytest.fixture
def make_client(repo, fake_producer, admin_consumer):
    def build(cors_origins: list[str] | None = None) -> TestClient:
        app = create_app(settings=ApiSettings(cors_origins=cors_origins or []), use_lifespan=False)
        producer = JsonProducer(KafkaSettings(bootstrap_servers="unused"), producer=fake_producer)
        app.dependency_overrides[get_repository] = lambda: repo
        app.dependency_overrides[get_producer] = lambda: producer
        app.dependency_overrides[get_admin_consumer] = lambda: admin_consumer
        return TestClient(app)

    return build


@pytest.fixture
def client(make_client) -> TestClient:
    return make_client()

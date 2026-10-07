import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from radar.common.kafka.consumer import TransientError
from radar.ingest import main as ingest_main
from radar.ingest.main import IngestHandler
from radar.ingest.writer import WriteStats
from tests.helpers.raw_posts import make_post


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture
def session():
    return FakeSession()


def test_handler_commits_once_per_batch(session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingest_main,
        "write_batch",
        lambda s, posts: calls.append(posts) or WriteStats(len(posts), 1, 0, 0),
    )

    IngestHandler(lambda: session)([make_post(), make_post("Stock.M.2.A.002")])

    assert session.commits == 1
    assert len(calls[0]) == 2


def test_handler_operational_error_becomes_transient(session, monkeypatch):
    def boom(s, posts):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    monkeypatch.setattr(ingest_main, "write_batch", boom)

    with pytest.raises(TransientError):
        IngestHandler(lambda: session)([make_post()])
    assert session.commits == 0


def test_handler_integrity_error_propagates(session, monkeypatch):
    def boom(s, posts):
        raise IntegrityError("INSERT", {}, Exception("violates check"))

    monkeypatch.setattr(ingest_main, "write_batch", boom)

    with pytest.raises(IntegrityError):
        IngestHandler(lambda: session)([make_post()])

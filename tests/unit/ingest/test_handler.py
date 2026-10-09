import pytest
from sqlalchemy.exc import DataError, IntegrityError, OperationalError, ProgrammingError

from radar.common.kafka.consumer import Rejection, TransientError
from radar.ingest import main as ingest_main
from radar.ingest.main import IngestHandler
from radar.ingest.writer import WriteStats
from tests.helpers.raw_posts import make_post


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


@pytest.fixture
def session():
    return FakeSession()


def test_handler_commits_once_per_batch(session, monkeypatch):
    calls = []
    monkeypatch.setattr(
        ingest_main,
        "write_batch",
        lambda s, posts: calls.append(posts) or WriteStats(len(posts), 1, 0, 0, 0),
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


def integrity_error(*args):
    raise IntegrityError("INSERT", {}, Exception("violates check"))


def test_handler_data_error_falls_back_to_write_each_and_returns_rejections(session, monkeypatch):
    rejection = Rejection(1, DataError("INSERT", {}, Exception("NUL")))
    monkeypatch.setattr(ingest_main, "write_batch", integrity_error)
    monkeypatch.setattr(
        ingest_main,
        "write_each",
        lambda s, posts: (WriteStats(len(posts), 1, 0, 0, 0), [rejection]),
    )

    result = IngestHandler(lambda: session)([make_post(), make_post("Stock.M.2.A.002")])

    assert result == [rejection]
    assert (session.rollbacks, session.commits) == (1, 1)


def test_handler_without_errors_returns_no_rejections(session, monkeypatch):
    monkeypatch.setattr(ingest_main, "write_batch", lambda s, posts: WriteStats(1, 1, 0, 0, 0))

    assert IngestHandler(lambda: session)([make_post()]) == []


def test_handler_other_db_error_propagates(session, monkeypatch):
    def boom(s, posts):
        raise ProgrammingError("INSERT", {}, Exception("column does not exist"))

    monkeypatch.setattr(ingest_main, "write_batch", boom)

    with pytest.raises(ProgrammingError):
        IngestHandler(lambda: session)([make_post()])
    assert session.commits == 0


def test_handler_operational_error_in_write_each_becomes_transient(session, monkeypatch):
    def down(s, posts):
        raise OperationalError("INSERT", {}, Exception("connection lost"))

    monkeypatch.setattr(ingest_main, "write_batch", integrity_error)
    monkeypatch.setattr(ingest_main, "write_each", down)

    with pytest.raises(TransientError):
        IngestHandler(lambda: session)([make_post()])
    assert session.commits == 0

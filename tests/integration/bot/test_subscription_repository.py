from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from radar.bot.repository import SubscriptionRepository
from radar.common.db.models import Subscription
from radar.common.db.session import make_engine, make_session_factory

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


@pytest.fixture
def sessions(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    engine = make_engine(postgres_env)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE subscriptions, boards CASCADE"))
        conn.execute(
            text(
                "INSERT INTO boards (board, interval_sec, recrawl_min_push, enabled) VALUES "
                "('Stock', 120, 0, true), ('Gossiping', 60, 10, true), ('Off', 60, 0, false)"
            )
        )
    yield make_session_factory(engine)
    engine.dispose()


def test_subscribe_inserts_once(sessions):
    with sessions() as s:
        repo = SubscriptionRepository(s)
        assert repo.subscribe(1, "Stock") is True
        assert repo.subscribe(1, "Stock") is False

    with sessions() as s:
        assert SubscriptionRepository(s).boards_of(1) == ["Stock"]


def test_unsubscribe_one_board(sessions):
    with sessions() as s:
        repo = SubscriptionRepository(s)
        repo.subscribe(1, "Stock")
        repo.subscribe(1, "Gossiping")

        assert repo.unsubscribe(1, "Stock") == 1
        assert repo.boards_of(1) == ["Gossiping"]


def test_unsubscribe_all(sessions):
    with sessions() as s:
        repo = SubscriptionRepository(s)
        repo.subscribe(1, "Stock")
        repo.subscribe(1, "Gossiping")
        repo.subscribe(2, "Stock")

        assert repo.unsubscribe(1, None) == 2
        assert (repo.boards_of(1), repo.boards_of(2)) == ([], ["Stock"])


def test_chats_for_board(sessions):
    with sessions() as s:
        repo = SubscriptionRepository(s)
        repo.subscribe(3, "Stock")
        repo.subscribe(1, "Stock")
        repo.subscribe(2, "Gossiping")

        assert repo.chats_for_board("Stock") == [1, 3]
        assert repo.chats_for_board("Off") == []


def test_enabled_boards_excludes_disabled(sessions):
    with sessions() as s:
        assert SubscriptionRepository(s).enabled_boards() == ["Gossiping", "Stock"]


def test_unit_type_check_rejects_unknown(sessions):
    with sessions() as s:
        s.add(Subscription(chat_id=1, unit_type="entity", unit_key="台積電"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_subscriptions_table_not_in_cdc_publication(sessions):
    with sessions() as s:
        tables = s.execute(
            text("SELECT tablename FROM pg_publication_tables WHERE pubname = 'radar_cdc'")
        ).scalars()

        assert "subscriptions" not in set(tables)

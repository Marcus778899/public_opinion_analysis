"""S6-02、S6-05：chat_settings、muted_posts 與推送對象的查詢。"""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from radar.bot.repository import PreferenceRepository, SubscriptionRepository
from radar.bot.views import ChatPrefs
from radar.common.db.models import MutedPost
from radar.common.db.session import make_engine, make_session_factory
from radar.common.schemas import Alert

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"
PID = "Stock.M.1792000000.A.ABC"
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)


@pytest.fixture
def sessions(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    engine = make_engine(postgres_env)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE subscriptions, chat_settings, muted_posts, boards CASCADE"))
        conn.execute(
            text(
                "INSERT INTO boards (board, interval_sec, recrawl_min_push, enabled) VALUES "
                "('Stock', 120, 0, true), ('Gossiping', 60, 10, true)"
            )
        )
    yield make_session_factory(engine)
    engine.dispose()


def alert(unit_type: str = "post", board: str = "Stock") -> Alert:
    return Alert(
        alert_id=uuid.uuid4(),
        unit_type=unit_type,  # type: ignore[arg-type]
        unit_key=PID if unit_type == "post" else board,
        board=board,
        window_start=NOW - timedelta(minutes=10),
        window_end=NOW,
        value=90,
        baseline=4,
        zscore=9,
        sample_post_ids=[PID],
        created_at=NOW,
    )


def test_prefs_default_all_on_without_writing(sessions):
    with sessions() as s:
        assert PreferenceRepository(s).prefs(1) == ChatPrefs()
        assert s.execute(text("SELECT count(*) FROM chat_settings")).scalar_one() == 0


def test_toggle_creates_row_then_flips_back(sessions):
    with sessions() as s:
        repo = PreferenceRepository(s)

        assert repo.toggle(1, "post") == ChatPrefs(post_alerts=False)
        assert repo.toggle(1, "post") == ChatPrefs()

    with sessions() as s:
        assert PreferenceRepository(s).prefs(1) == ChatPrefs()


def test_mute_twice_and_unmute(sessions):
    with sessions() as s:
        repo = PreferenceRepository(s)

        assert (repo.mute(1, PID), repo.mute(1, PID)) == (True, False)
        assert repo.muted(1) == [PID]
        assert (repo.unmute(1, PID), repo.unmute(1, PID)) == (True, False)


def test_muted_newest_first(sessions):
    with sessions() as s:
        s.add_all(
            [
                MutedPost(chat_id=1, post_id="Stock.M.1.A.111", muted_at=NOW - timedelta(hours=1)),
                MutedPost(chat_id=1, post_id="Stock.M.2.A.222", muted_at=NOW),
            ]
        )
        s.commit()

        assert PreferenceRepository(s).muted(1) == ["Stock.M.2.A.222", "Stock.M.1.A.111"]


def test_purge_muted_deletes_only_older_rows(sessions):
    with sessions() as s:
        s.add_all(
            [
                MutedPost(chat_id=1, post_id="Stock.M.1.A.111", muted_at=NOW - timedelta(hours=49)),
                MutedPost(chat_id=1, post_id="Stock.M.2.A.222", muted_at=NOW),
            ]
        )
        s.commit()
        repo = PreferenceRepository(s)

        assert repo.purge_muted(NOW - timedelta(hours=48)) == 1
        assert repo.muted(1) == ["Stock.M.2.A.222"]


def test_recipients_filters_subscription_type_and_mute(sessions):
    with sessions() as s:
        subs, prefs = SubscriptionRepository(s), PreferenceRepository(s)
        for chat in (1, 2, 3, 4):
            subs.subscribe(chat, "Stock")
        subs.subscribe(5, "Gossiping")
        prefs.toggle(2, "post")  # 2 關閉文章警示
        prefs.toggle(3, "board")  # 3 關閉看板警示
        prefs.mute(4, PID)  # 4 不再通知這篇

        assert prefs.recipients(alert("post")) == [1, 3]
        assert prefs.recipients(alert("board")) == [1, 2, 4]


def test_recipients_no_subscribers(sessions):
    with sessions() as s:
        assert PreferenceRepository(s).recipients(alert()) == []


def test_forget_removes_subscriptions_settings_and_mutes(sessions):
    with sessions() as s:
        SubscriptionRepository(s).subscribe(1, "Stock")
        SubscriptionRepository(s).subscribe(2, "Stock")
        repo = PreferenceRepository(s)
        repo.toggle(1, "post")
        repo.mute(1, PID)

        repo.forget(1)

        counts = [
            s.execute(text(f"SELECT count(*) FROM {t} WHERE chat_id = 1")).scalar_one()
            for t in ("subscriptions", "chat_settings", "muted_posts")
        ]
        assert counts == [0, 0, 0]
        assert repo.recipients(alert("board")) == [2]


def test_new_tables_not_in_cdc_publication(sessions):
    with sessions() as s:
        tables = set(
            s.execute(
                text("SELECT tablename FROM pg_publication_tables WHERE pubname = 'radar_cdc'")
            ).scalars()
        )

        assert not {"chat_settings", "muted_posts"} & tables

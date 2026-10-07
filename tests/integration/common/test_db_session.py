from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from radar.common.db.session import make_engine, make_session_factory

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "alembic.ini"


def test_session_factory_connects_and_runs_select_1(postgres_env):
    engine = make_engine(postgres_env)
    session_factory = make_session_factory(engine)

    with session_factory() as session:
        assert session.execute(text("SELECT 1")).scalar_one() == 1
    engine.dispose()


def test_alembic_upgrade_head_on_empty_db(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")

    engine = make_engine(postgres_env)
    assert "alembic_version" in inspect(engine).get_table_names()
    engine.dispose()

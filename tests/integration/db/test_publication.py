import json
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from radar.common.db.session import make_engine

REPO = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO / "alembic.ini"
CONNECTOR_FILE = REPO / "infra/debezium/radar-cdc.json"


@pytest.fixture
def alembic_cfg(postgres_env) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    command.upgrade(cfg, "head")
    yield cfg
    command.upgrade(cfg, "head")


@pytest.fixture
def engine(postgres_env, alembic_cfg) -> Engine:
    eng = make_engine(postgres_env)
    yield eng
    eng.dispose()


def _published_tables(engine: Engine, name: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tablename FROM pg_publication_tables WHERE pubname = :n"), {"n": name}
        )
        return {r[0] for r in rows}


def test_publication_includes_only_posts_and_comments(engine):
    name = json.loads(CONNECTOR_FILE.read_text())["config"]["publication.name"]

    assert _published_tables(engine, name) == {"posts", "comments"}


def test_downgrade_drops_publication(alembic_cfg, engine):
    command.downgrade(alembic_cfg, "-1")

    assert _published_tables(engine, "radar_cdc") == set()

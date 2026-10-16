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
# 建立 publication 之前的版本；之後的 migration 增加時不必改這裡
PUBLICATION_DOWN_REVISION = "4856307c62e5"


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
    command.downgrade(alembic_cfg, PUBLICATION_DOWN_REVISION)

    assert _published_tables(engine, "radar_cdc") == set()


def _replica_identity(engine: Engine, table: str) -> str:
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT relreplident FROM pg_class WHERE relname = :t"), {"t": table}
        ).scalar_one()


def test_comments_replica_identity_is_full(engine):
    # f = FULL，d = DEFAULT；posts 不會被刪，維持預設
    assert (_replica_identity(engine, "comments"), _replica_identity(engine, "posts")) == ("f", "d")


def test_downgrade_restores_default_replica_identity(alembic_cfg, engine):
    command.downgrade(alembic_cfg, "a3c1f0d2b7e4")

    assert _replica_identity(engine, "comments") == "d"

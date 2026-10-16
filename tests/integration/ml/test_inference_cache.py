"""#37：推論快取從 ClickHouse 載入、補舊 hash，在真的 ClickHouse 與 PG 上的行為。

不需要 Kafka：直接把資料寫進 predictions。Kafka engine 表連不上 broker 只會記 log。
migration 0004 本身（queue、MV）的測試在 tests/integration/cdc/test_clickhouse_migrations.py。
"""

import time
from pathlib import Path

import httpx2
import pytest
from alembic import command
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import text
from testcontainers.core.container import DockerContainer

from radar.common.clickhouse import ClickHouseClient, apply_pending, load_migrations
from radar.common.db.session import make_engine
from radar.common.settings import ClickHouseSettings
from radar.ml.inference.backfill_hash import (
    apply_updates,
    build_updates,
    fetch_missing,
    fetch_texts,
)
from radar.ml.inference.main import HashCache, load_cache, text_hash
from radar.ml.training.dataset import post_text

REPO = Path(__file__).resolve().parents[3]
CH_DIR = REPO / "infra/clickhouse"
ALEMBIC_INI = REPO / "alembic.ini"
MV = "tfidf-lr-1"
MAX_CHARS = 2000
H_OLD, H_NEW = "1" * 64, "2" * 64


@pytest.fixture(scope="module")
def ch():
    container = (
        DockerContainer("clickhouse/clickhouse-server:26.8")
        .with_env("CLICKHOUSE_USER", "radar")
        .with_env("CLICKHOUSE_PASSWORD", "it")
        .with_env("CLICKHOUSE_DB", "radar")
        .with_volume_mapping(
            str(CH_DIR / "config.d/named_collections.xml"),
            "/etc/clickhouse-server/config.d/named_collections.xml",
        )
        .with_volume_mapping(
            str(CH_DIR / "users.d/radar.xml"), "/etc/clickhouse-server/users.d/radar.xml"
        )
        .with_exposed_ports(8123)
    )
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8123)}"
        deadline = time.monotonic() + 60
        while True:
            try:
                if httpx2.get(f"{url}/ping").status_code == 200:
                    break
            except httpx2.TransportError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError("clickhouse not ready")
            time.sleep(1)
        client = ClickHouseClient(
            ClickHouseSettings(url=url, db="radar", user="radar", password=SecretStr("it"))
        )
        apply_pending(client, load_migrations(CH_DIR / "migrations"))
        yield client
        client.close()


@pytest.fixture
def predictions(ch):
    ch.execute("TRUNCATE TABLE predictions")
    return ch


def insert(ch: ClickHouseClient, post_id: str, at: str, digest: str = "", mv: str = MV) -> None:
    ch.execute(
        "INSERT INTO predictions (post_id, model_version, predicted_at, polarity, scores, "
        f"text_hash) VALUES ('{post_id}', '{mv}', '{at}', 'neutral', map('neutral', 1.0), "
        f"'{digest}')"
    )


def hashes(ch: ClickHouseClient) -> list[list[str]]:
    rows = ch.execute(
        "SELECT post_id, toString(predicted_at), text_hash FROM predictions "
        "ORDER BY post_id, predicted_at FORMAT TSV"
    )
    return [line.split("\t") for line in rows.splitlines()]


@pytest.fixture
def engine(postgres_env):
    command.upgrade(Config(str(ALEMBIC_INI)), "head")
    eng = make_engine(postgres_env)
    with eng.begin() as conn:
        conn.execute(text("TRUNCATE boards, crawl_state, comments, posts CASCADE"))
    yield eng
    eng.dispose()


def add_post(engine, post_id: str, title: str, content: str, deleted: bool = False) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO posts (post_id, board, url, title, content, created_at, crawled_at, "
                "is_deleted) VALUES (:id, :board, :url, :title, :content, now(), now(), :deleted)"
            ),
            {
                "id": post_id,
                "board": post_id.split(".", 1)[0],
                "url": f"https://www.ptt.cc/bbs/x/{post_id}.html",
                "title": title,
                "content": content,
                "deleted": deleted,
            },
        )


# --- load_cache ---


def test_load_cache_takes_latest_hash_per_post_of_model_version(predictions):
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 01:00:00", H_OLD)
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 02:00:00", H_NEW)
    insert(predictions, "Stock.M.2.A.222", "2026-10-16 03:00:00", H_OLD, mv="other-model")
    cache = HashCache(100)

    loaded = load_cache(predictions, MV, cache)

    assert loaded == 1
    assert cache.get("Stock.M.1.A.111") == H_NEW
    assert cache.get("Stock.M.2.A.222") is None


def test_load_cache_ignores_rows_without_hash(predictions):
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 01:00:00", H_OLD)
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 02:00:00", "")
    insert(predictions, "Stock.M.3.A.333", "2026-10-16 01:00:00", "")
    cache = HashCache(100)

    load_cache(predictions, MV, cache)

    # 最新一筆沒有 hash 時，退回有 hash 的較舊一筆
    assert cache.get("Stock.M.1.A.111") == H_OLD
    assert cache.get("Stock.M.3.A.333") is None


# --- backfill ---


def backfill(ch: ClickHouseClient, engine) -> int:
    missing = fetch_missing(ch, MV)
    texts = fetch_texts(engine, [m.post_id for m in missing], MAX_CHARS)
    return apply_updates(ch, MV, build_updates(missing, texts), batch_size=1)


def test_backfill_fills_only_latest_prediction_per_post_from_pg_text(predictions, engine):
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 01:00:00.000001")
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 02:00:00.123456")
    insert(predictions, "Stock.M.2.A.222", "2026-10-16 01:00:00")
    add_post(engine, "Stock.M.1.A.111", "標題", "內文")
    add_post(engine, "Stock.M.2.A.222", "t2", "c2")

    assert backfill(predictions, engine) == 2

    h1 = text_hash(post_text("標題", "內文", MAX_CHARS))
    h2 = text_hash(post_text("t2", "c2", MAX_CHARS))
    assert hashes(predictions) == [
        ["Stock.M.1.A.111", "2026-10-16 01:00:00.000001", ""],
        ["Stock.M.1.A.111", "2026-10-16 02:00:00.123456", h1],
        ["Stock.M.2.A.222", "2026-10-16 01:00:00.000000", h2],
    ]
    cache = HashCache(10)
    load_cache(predictions, MV, cache)
    assert len(cache) == 2


def test_backfill_twice_is_noop(predictions, engine):
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 01:00:00")
    add_post(engine, "Stock.M.1.A.111", "標題", "內文")
    backfill(predictions, engine)
    before = hashes(predictions)

    assert fetch_missing(predictions, MV) == []
    assert backfill(predictions, engine) == 0
    assert hashes(predictions) == before


def test_backfill_does_not_touch_rows_that_already_have_hash(predictions, engine):
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 01:00:00", H_OLD)
    add_post(engine, "Stock.M.1.A.111", "標題", "編輯後的內文")

    assert backfill(predictions, engine) == 0
    assert hashes(predictions) == [["Stock.M.1.A.111", "2026-10-16 01:00:00.000000", H_OLD]]


def test_backfill_skips_post_deleted_in_pg(predictions, engine):
    insert(predictions, "Stock.M.1.A.111", "2026-10-16 01:00:00")
    insert(predictions, "Stock.M.2.A.222", "2026-10-16 01:00:00")
    add_post(engine, "Stock.M.1.A.111", "標題", "內文", deleted=True)

    assert backfill(predictions, engine) == 0
    assert [r[2] for r in hashes(predictions)] == ["", ""]

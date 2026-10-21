"""ClickHouse migration 與 JSON topic 接入（S2-05、S2-06）。

CDC 的 Avro 路徑需要 Connect + Apicurio，由 tests/e2e 驗證；這裡只驗證 DDL 與 JSON topic。
"""

import json
import time
from pathlib import Path

import pytest
from confluent_kafka import Producer

from radar.common.clickhouse import (
    MIGRATIONS_TABLE,
    ClickHouseClient,
    apply_pending,
    load_migrations,
)
from tests.helpers.clickhouse import drop_queue_tables, without_kafka

# NOTE: 用共用的 radar database 與固定名稱的 topic（Kafka engine 表），整個模組固定在同一個 worker
pytestmark = pytest.mark.xdist_group("shared_radar_db")

REPO = Path(__file__).resolve().parents[3]
CLICKHOUSE_DIR = REPO / "infra/clickhouse"


@pytest.fixture(scope="module")
def kafka(kafka_settings):
    # NOTE: JSON topic 已由 session 重置建好（ClickHouse 的 Kafka engine 表要先有 topic）
    return kafka_settings


@pytest.fixture(scope="module")
def ch(shared_clickhouse):
    apply_pending(shared_clickhouse, load_migrations(CLICKHOUSE_DIR / "migrations"))
    return shared_clickhouse


def _query(ch: ClickHouseClient, sql: str) -> list[list[str]]:
    return [line.split("\t") for line in ch.execute(f"{sql} FORMAT TSV").splitlines()]


def _wait_rows(ch: ClickHouseClient, table: str, expected: int, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if int(ch.execute(f"SELECT count() FROM {table}")) >= expected:
            return
        time.sleep(1)
    raise AssertionError(f"{table} has fewer than {expected} rows after {timeout_s}s")


def test_apply_pending_creates_all_tables_and_views(ch):
    tables = {r[0] for r in _query(ch, "SELECT name FROM system.tables WHERE database = 'radar'")}

    targets = {
        "posts_latest",
        "posts_history",
        "comments_latest",
        "labels",
        "predictions",
        "alerts",
    }
    queues = {"posts_queue", "comments_queue", "labels_queue", "predictions_queue", "alerts_queue"}
    views = {
        "posts_latest_mv",
        "posts_history_mv",
        "comments_latest_mv",
        "labels_mv",
        "predictions_mv",
        "alerts_mv",
    }
    assert targets | queues | views <= tables
    assert not {"comments", "comments_mv"} & tables  # 0003 已換成 comments_latest


def test_apply_pending_twice_is_noop(ch):
    migrations = load_migrations(CLICKHOUSE_DIR / "migrations")

    assert apply_pending(ch, migrations) == []
    versions = _query(ch, f"SELECT version FROM {MIGRATIONS_TABLE} ORDER BY version")
    assert [int(v[0]) for v in versions] == [m.version for m in migrations]


def test_posts_latest_final_keeps_highest_lsn(ch):
    cols = "post_id, board, url, push_count, boo_count, created_at, crawled_at, is_deleted, lsn"
    ts = "'2026-10-07 00:00:00'"
    ch.execute(
        f"INSERT INTO posts_latest ({cols}) VALUES "
        f"('Stock.M.9.A.1', 'Stock', 'u', 30, 0, {ts}, {ts}, false, 300), "
        f"('Stock.M.9.A.1', 'Stock', 'u', 10, 0, {ts}, {ts}, false, 100)"
    )

    rows = _query(ch, "SELECT push_count FROM posts_latest FINAL WHERE post_id = 'Stock.M.9.A.1'")

    assert rows == [["30"]]


COMMENT_COLS = "post_id, board, floor, type, changed_at, lsn"


def test_comments_latest_final_keeps_highest_lsn_and_drops_deleted(ch):
    ts = "'2026-10-07 00:00:00'"
    ch.execute(
        f"INSERT INTO comments_latest ({COMMENT_COLS}, user_id, is_deleted) VALUES "
        f"('Stock.M.9.A.2', 'Stock', 1, 'push', {ts}, 100, 'old', 0), "
        f"('Stock.M.9.A.2', 'Stock', 1, 'push', {ts}, 300, 'new', 0), "
        f"('Stock.M.9.A.2', 'Stock', 2, 'push', {ts}, 100, 'gone', 0), "
        f"('Stock.M.9.A.2', 'Stock', 2, 'push', {ts}, 300, 'gone', 1)"
    )

    rows = _query(
        ch, "SELECT floor, user_id FROM comments_latest FINAL WHERE post_id = 'Stock.M.9.A.2'"
    )

    assert rows == [["1", "new"]]


def test_json_topic_rows_land_in_target_tables(kafka, ch):
    producer = Producer({"bootstrap.servers": kafka.bootstrap_servers})
    messages = {
        "labels": {
            "schema_version": 1,
            "post_id": "Stock.M.1.A.1",
            "labeler": "gemini-flash",
            "version": "prompt-v1",
            "labeled_at": "2026-10-07T06:00:00Z",
            "sentiments": [
                {"target": None, "polarity": "negative"},
                {"target": "台積電", "polarity": "positive"},
            ],
        },
        "predictions": {
            "schema_version": 1,
            "post_id": "Stock.M.1.A.1",
            "model_version": "tfidf-lr-1",
            "predicted_at": "2026-10-07T06:00:00.123456+00:00",
            "polarity": "negative",
            "scores": {"positive": 0.1, "negative": 0.7, "neutral": 0.2},
        },
        "alerts": {
            "schema_version": 1,
            "alert_id": "0b6c1f8e-3a5e-4c1e-9d0a-2f4b8c9e7a11",
            "unit_type": "post",
            "unit_key": "Stock.M.1.A.1",
            "board": "Stock",
            "window_start": "2026-10-07T05:55:00Z",
            "window_end": "2026-10-07T06:00:00Z",
            "value": 85,
            "baseline": 6.2,
            "zscore": 7.4,
            "sample_post_ids": ["Stock.M.1.A.1"],
            "created_at": "2026-10-07T06:00:01Z",
            "unknown_future_field": "ignored",
        },
    }
    for topic, body in messages.items():
        producer.produce(
            topic,
            key=body["post_id" if "post_id" in body else "unit_key"],
            value=json.dumps(body, ensure_ascii=False).encode(),
        )
    producer.flush(10)

    _wait_rows(ch, "labels WHERE post_id = 'Stock.M.1.A.1'", 2)
    _wait_rows(ch, "predictions WHERE post_id = 'Stock.M.1.A.1'", 1)
    # NOTE: heat 測試也會寫 alerts topic，所以只看這則訊息的 unit_key
    _wait_rows(ch, "alerts WHERE unit_key = 'Stock.M.1.A.1'", 1)

    assert sorted(
        _query(
            ch,
            "SELECT ifNull(target, '<whole>'), polarity FROM labels "
            "WHERE post_id = 'Stock.M.1.A.1'",
        )
    ) == [
        ["<whole>", "negative"],
        ["台積電", "positive"],
    ]
    # 0004 之前的訊息沒有 text_hash，存成空字串（開發規格 3.5）
    assert _query(
        ch,
        "SELECT predicted_at, scores['negative'], text_hash FROM predictions "
        "WHERE post_id = 'Stock.M.1.A.1'",
    ) == [["2026-10-07 06:00:00.123456", "0.7", ""]]
    sql = "SELECT unit_key, window_end, zscore FROM alerts WHERE unit_key = 'Stock.M.1.A.1'"
    assert _query(ch, sql) == [["Stock.M.1.A.1", "2026-10-07 06:00:00.000000", "7.4"]]


def test_predictions_text_hash_lands_in_table(kafka, ch):
    producer = Producer({"bootstrap.servers": kafka.bootstrap_servers})
    body = {
        "schema_version": 1,
        "post_id": "Stock.M.2.A.2",
        "model_version": "tfidf-lr-1",
        "predicted_at": "2026-10-16T06:00:00+00:00",
        "polarity": "neutral",
        "scores": {"positive": 0.1, "negative": 0.2, "neutral": 0.7},
        "text_hash": "a" * 64,
    }
    producer.produce("predictions", key=body["post_id"], value=json.dumps(body).encode())
    producer.flush(10)

    deadline = time.monotonic() + 60
    sql = "SELECT text_hash FROM predictions WHERE post_id = 'Stock.M.2.A.2'"
    while not (rows := _query(ch, sql)) and time.monotonic() < deadline:
        time.sleep(1)
    assert rows == [["a" * 64]]


# NOTE: 以下兩個測試另建 database；0004 的 queue 表與 radar 同 consumer group，會搶走 partition，
# 刪掉後 broker 要等一陣子才重新分配，所以排在會等 Kafka 資料的測試之後；0003 不建 Kafka 表
def test_migration_0003_copies_existing_comments(clickhouse_settings):
    # 獨立的 database：先套到 0002、寫入舊的 comments，再套 0003
    admin = ClickHouseClient(clickhouse_settings)
    admin.execute("CREATE DATABASE IF NOT EXISTS copy_test")
    client = ClickHouseClient(clickhouse_settings.model_copy(update={"db": "copy_test"}))
    migrations = load_migrations(CLICKHOUSE_DIR / "migrations")
    try:
        apply_pending(client, without_kafka([m for m in migrations if m.version < 3]))
        client.execute(
            f"INSERT INTO comments ({COMMENT_COLS}) VALUES "
            "('Stock.M.9.A.3', 'Stock', 1, 'push', '2026-10-07 00:00:00', 42)"
        )

        apply_pending(client, without_kafka(migrations))

        rows = _query(client, "SELECT floor, lsn, is_deleted FROM comments_latest FINAL")
        assert rows == [["1", "42", "0"]]
    finally:
        admin.execute("DROP DATABASE IF EXISTS copy_test")
        client.close()
        admin.close()


def test_migration_0004_keeps_existing_predictions_with_empty_hash(clickhouse_settings):
    # 獨立的 database：先套到 0003、寫入舊的 predictions，再套 0004
    admin = ClickHouseClient(clickhouse_settings)
    admin.execute("CREATE DATABASE IF NOT EXISTS hash_test")
    client = ClickHouseClient(clickhouse_settings.model_copy(update={"db": "hash_test"}))
    migrations = load_migrations(CLICKHOUSE_DIR / "migrations")
    try:
        apply_pending(client, [m for m in migrations if m.version < 4])
        client.execute(
            "INSERT INTO predictions (post_id, model_version, predicted_at, polarity, scores) "
            "VALUES ('Stock.M.9.A.4', 'v1', '2026-10-16 00:00:00', 'neutral', map('neutral', 1.0))"
        )

        apply_pending(client, migrations)
        views = _query(client, "SELECT name FROM system.tables WHERE database = 'hash_test'")
        drop_queue_tables(client, "hash_test")

        assert _query(client, "SELECT post_id, text_hash FROM predictions") == [
            ["Stock.M.9.A.4", ""]
        ]
        assert {"predictions_queue", "predictions_mv"} <= {r[0] for r in views}
    finally:
        admin.execute("DROP DATABASE IF EXISTS hash_test")
        client.close()
        admin.close()

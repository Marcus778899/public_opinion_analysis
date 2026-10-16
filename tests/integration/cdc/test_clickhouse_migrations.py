"""ClickHouse migration 與 JSON topic 接入（S2-05、S2-06）。

CDC 的 Avro 路徑需要 Connect + Apicurio，由 tests/e2e 驗證；這裡只驗證 DDL 與 JSON topic。
"""

import json
import time
from pathlib import Path

import httpx2
import pytest
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient, NewTopic
from pydantic import SecretStr
from testcontainers.community.kafka import KafkaContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from radar.common.clickhouse import (
    MIGRATIONS_TABLE,
    ClickHouseClient,
    apply_pending,
    load_migrations,
)
from radar.common.settings import ClickHouseSettings

REPO = Path(__file__).resolve().parents[3]
CLICKHOUSE_DIR = REPO / "infra/clickhouse"
CLICKHOUSE_IMAGE = "clickhouse/clickhouse-server:26.8"
COMPOSE_BROKERS = "kafka_1:29092,kafka_2:29092,kafka_3:29092"
JSON_TOPICS = ["labels", "predictions", "alerts"]


@pytest.fixture(scope="module")
def network():
    with Network() as net:
        yield net


@pytest.fixture(scope="module")
def kafka(network):
    # NOTE: KRaft 的 controller 位址取自 network alias，沒設會連不上自己
    kafka_container = (
        KafkaContainer().with_kraft().with_network(network).with_network_aliases("kafka")
    )
    with kafka_container as k:
        admin = AdminClient({"bootstrap.servers": k.get_bootstrap_server()})
        futures = admin.create_topics([NewTopic(t, num_partitions=1) for t in JSON_TOPICS])
        for f in futures.values():
            f.result(30)
        yield k


@pytest.fixture(scope="module")
def clickhouse_settings(network, kafka, tmp_path_factory):
    # NOTE: named collection 寫死 compose 的 broker；改成測試 Kafka 在 docker 網路內的位址
    ip = kafka.get_wrapped_container().attrs["NetworkSettings"]["Networks"][network.name][
        "IPAddress"
    ]
    xml = (CLICKHOUSE_DIR / "config.d/named_collections.xml").read_text()
    assert COMPOSE_BROKERS in xml
    named = tmp_path_factory.mktemp("ch") / "named_collections.xml"
    named.write_text(xml.replace(COMPOSE_BROKERS, f"{ip}:9092"))

    container = (
        DockerContainer(CLICKHOUSE_IMAGE)
        .with_network(network)
        .with_env("CLICKHOUSE_USER", "radar")
        .with_env("CLICKHOUSE_PASSWORD", "it")
        .with_env("CLICKHOUSE_DB", "radar")
        .with_volume_mapping(str(named), "/etc/clickhouse-server/config.d/named_collections.xml")
        .with_volume_mapping(
            str(CLICKHOUSE_DIR / "users.d/radar.xml"), "/etc/clickhouse-server/users.d/radar.xml"
        )
        .with_exposed_ports(8123)
    )
    with container:
        url = f"http://{container.get_container_host_ip()}:{container.get_exposed_port(8123)}"
        _wait_for_ping(url)
        yield ClickHouseSettings(url=url, db="radar", user="radar", password=SecretStr("it"))


def _wait_for_ping(url: str, timeout_s: float = 60.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if httpx2.get(f"{url}/ping").status_code == 200:
                return
        except httpx2.TransportError:
            pass
        time.sleep(1)
    raise TimeoutError("clickhouse not ready")


@pytest.fixture(scope="module")
def ch(clickhouse_settings):
    client = ClickHouseClient(clickhouse_settings)
    apply_pending(client, load_migrations(CLICKHOUSE_DIR / "migrations"))
    yield client
    client.close()


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


def test_migration_0003_copies_existing_comments(clickhouse_settings):
    # 獨立的 database：先套到 0002、寫入舊的 comments，再套 0003
    admin = ClickHouseClient(clickhouse_settings)
    admin.execute("CREATE DATABASE IF NOT EXISTS copy_test")
    client = ClickHouseClient(clickhouse_settings.model_copy(update={"db": "copy_test"}))
    migrations = load_migrations(CLICKHOUSE_DIR / "migrations")
    try:
        apply_pending(client, [m for m in migrations if m.version < 3])
        client.execute(
            f"INSERT INTO comments ({COMMENT_COLS}) VALUES "
            "('Stock.M.9.A.3', 'Stock', 1, 'push', '2026-10-07 00:00:00', 42)"
        )

        apply_pending(client, migrations)

        rows = _query(client, "SELECT floor, lsn, is_deleted FROM comments_latest FINAL")
        assert rows == [["1", "42", "0"]]
    finally:
        admin.execute("DROP DATABASE IF EXISTS copy_test")
        client.close()
        admin.close()


def test_json_topic_rows_land_in_target_tables(kafka, ch):
    producer = Producer({"bootstrap.servers": kafka.get_bootstrap_server()})
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

    _wait_rows(ch, "labels", 2)
    _wait_rows(ch, "predictions", 1)
    _wait_rows(ch, "alerts", 1)

    assert sorted(_query(ch, "SELECT ifNull(target, '<whole>'), polarity FROM labels")) == [
        ["<whole>", "negative"],
        ["台積電", "positive"],
    ]
    assert _query(ch, "SELECT predicted_at, scores['negative'] FROM predictions") == [
        ["2026-10-07 06:00:00.123456", "0.7"]
    ]
    assert _query(ch, "SELECT unit_key, window_end, zscore FROM alerts") == [
        ["Stock.M.1.A.1", "2026-10-07 06:00:00.000000", "7.4"]
    ]

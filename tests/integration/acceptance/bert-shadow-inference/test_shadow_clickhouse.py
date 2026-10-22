"""bert-shadow-inference 驗收：predictions.shadow 進 predictions_shadow，不進 predictions。

用共用 radar database 與固定名稱的 topic（Kafka engine 表），模組固定在同一個 worker。
"""

import json
import time
from pathlib import Path

import pytest
from confluent_kafka import Producer

from radar.common.clickhouse import ClickHouseClient, apply_pending, load_migrations
from radar.common.kafka import names
from tests.integration import conftest as integration_conftest

pytestmark = pytest.mark.xdist_group("shared_radar_db")

REPO = Path(__file__).resolve().parents[4]
POST_ID = "Stock.M.3.A.3"


@pytest.fixture(scope="module")
def ch(shared_clickhouse):
    apply_pending(shared_clickhouse, load_migrations(REPO / "infra/clickhouse/migrations"))
    return shared_clickhouse


def count(ch: ClickHouseClient, table: str) -> int:
    return int(ch.execute(f"SELECT count() FROM {table} WHERE post_id = '{POST_ID}'"))


def test_clickhouse_topics_include_predictions_shadow():
    assert names.PREDICTIONS_SHADOW in integration_conftest.CLICKHOUSE_TOPICS


def test_shadow_prediction_lands_in_predictions_shadow_and_not_in_predictions(kafka_settings, ch):
    body = {
        "schema_version": 1,
        "post_id": POST_ID,
        "model_version": "bert-it-shadow",
        "predicted_at": "2026-10-21T06:00:00+00:00",
        "polarity": "negative",
        "scores": {"positive": 0.1, "negative": 0.7, "neutral": 0.2},
        "text_hash": "b" * 64,
    }
    producer = Producer({"bootstrap.servers": kafka_settings.bootstrap_servers})
    producer.produce(names.PREDICTIONS_SHADOW, key=POST_ID, value=json.dumps(body).encode())
    assert producer.flush(10) == 0

    deadline = time.monotonic() + 60
    while count(ch, "predictions_shadow") < 1 and time.monotonic() < deadline:
        time.sleep(1)

    assert count(ch, "predictions_shadow") == 1
    assert count(ch, "predictions") == 0
    rows = ch.execute(
        f"SELECT model_version, text_hash FROM predictions_shadow WHERE post_id = '{POST_ID}' "
        "FORMAT TSV"
    )
    assert rows.strip() == f"bert-it-shadow\t{'b' * 64}"

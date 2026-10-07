from confluent_kafka import KafkaError, KafkaException

from radar.api.schemas import BoardStatus
from tests.unit.api.conftest import NOW


def test_status_combines_board_stats_and_dlq_count(client, repo):
    repo.status_rows = [
        BoardStatus(board="Stock", enabled=True, last_changed_at=NOW, post_count_24h=5)
    ]

    body = client.get("/status").json()

    assert body["dlq_count"] == 5  # (3 - 0) + (4 - 2)
    assert body["boards"][0]["board"] == "Stock"
    assert body["boards"][0]["post_count_24h"] == 5


def test_status_dlq_unavailable_returns_minus_one(make_client, admin_consumer):
    admin_consumer.error = KafkaException(KafkaError(KafkaError._TRANSPORT))

    response = make_client().get("/status")

    assert response.status_code == 200
    assert response.json()["dlq_count"] == -1


def test_status_without_dlq_topic_returns_zero(make_client, admin_consumer):
    admin_consumer.dlq_watermarks = {}

    assert make_client().get("/status").json()["dlq_count"] == 0

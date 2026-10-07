import json

from radar.api.kafka_ops import count_dlq_messages, dispatch_task, make_manual_list_task
from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.settings import KafkaSettings
from tests.unit.api.conftest import FakeAdminConsumer
from tests.unit.common.kafka.fakes import FakeProducer


def test_make_manual_list_task_fields():
    task = make_manual_list_task("Gossiping")

    assert (task.type, task.reason, task.board) == (
        CrawlTaskType.LIST,
        CrawlReason.MANUAL,
        "Gossiping",
    )
    assert task.url == "https://www.ptt.cc/bbs/Gossiping/index.html"
    assert task.post_id is None
    assert task.created_at.tzinfo is not None


def test_make_manual_list_task_ids_are_unique():
    assert make_manual_list_task("Stock").task_id != make_manual_list_task("Stock").task_id


def test_dispatch_task_uses_kafka_key_and_flushes():
    fake = FakeProducer()
    task = make_manual_list_task("Stock")

    dispatch_task(JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=fake), task)

    assert fake.produced[0]["topic"] == names.CRAWL_TASKS
    assert fake.produced[0]["key"] == b"Stock"
    assert json.loads(fake.produced[0]["value"])["task_id"] == str(task.task_id)
    assert fake._pending == []


def test_count_dlq_messages_sums_watermarks():
    assert count_dlq_messages(FakeAdminConsumer({0: (0, 3), 1: (2, 4), 2: (5, 5)})) == 5


def test_count_dlq_messages_missing_topic_returns_zero():
    assert count_dlq_messages(FakeAdminConsumer({})) == 0

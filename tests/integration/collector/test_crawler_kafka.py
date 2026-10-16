import contextlib
import uuid
from datetime import UTC, datetime

from confluent_kafka import Consumer
from confluent_kafka.admin import AdminClient, NewTopic

from radar.collector.crawler import CrawlHandler
from radar.collector.fetch_cache import RecentFetches
from radar.collector.list_cache import ListPushCache
from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names
from radar.common.kafka.config import admin_config, consumer_config
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import CrawlTask, RawHtml, RawPost
from tests.unit.collector.conftest import INDEX_URL, FakeFetcher

NOW = datetime(2026, 10, 7, 5, 0, tzinfo=UTC)


def ensure_topics(settings):
    admin = AdminClient(admin_config(settings))
    futures = admin.create_topics([NewTopic(t, 1, 1) for t in (names.RAW_POSTS, names.RAW_HTML)])
    for future in futures.values():
        with contextlib.suppress(Exception):  # 其他測試可能已建立
            future.result()


def read_all(settings, topic, model, expected):
    consumer = Consumer(consumer_config(settings, f"it-{uuid.uuid4().hex[:6]}"))
    consumer.subscribe([topic])
    items = []
    for _ in range(30):
        msg = consumer.poll(1.0)
        if msg is not None and msg.error() is None:
            items.append((msg.key().decode(), model.model_validate_json(msg.value())))
        if len(items) >= expected:
            break
    consumer.close()
    return items


def test_crawl_task_to_raw_posts_through_kafka(kafka_settings):
    ensure_topics(kafka_settings)
    producer = JsonProducer(kafka_settings)
    handler = CrawlHandler(
        FakeFetcher(), producer, ListPushCache(), RecentFetches(), clock=lambda: NOW
    )
    task = CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.LIST,
        board="Stock",
        url=INDEX_URL,
        reason=CrawlReason.SCHEDULE,
        created_at=NOW,
    )

    handler([task])

    posts = read_all(kafka_settings, names.RAW_POSTS, RawPost, 3)
    htmls = read_all(kafka_settings, names.RAW_HTML, RawHtml, 3)
    assert len(posts) >= 3 and len(htmls) >= 3
    assert all(key == post.post_id for key, post in posts)
    assert {post.task_id for _, post in posts} == {task.task_id}

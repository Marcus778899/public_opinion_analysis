import json
import uuid
from datetime import UTC, datetime

import pytest

from radar.collector.crawler import CrawlHandler, deleted_post
from radar.collector.http import FetchError
from radar.collector.list_cache import ListPushCache
from radar.collector.parsers.ptt import ListEntry
from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names
from radar.common.kafka.consumer import TransientError
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import CrawlTask, RawPost
from radar.common.settings import KafkaSettings
from tests.unit.collector.conftest import INDEX_URL, PREV_URL, read_fixture
from tests.unit.common.kafka.fakes import FakeProducer

NOW = datetime(2026, 10, 7, 5, 0, tzinfo=UTC)
POST_URL = "https://www.ptt.cc/bbs/Stock/M.1791345103.A.E41.html"
POST_ID = "Stock.M.1791345103.A.E41"


def list_task():
    return CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.LIST,
        board="Stock",
        url=INDEX_URL,
        reason=CrawlReason.SCHEDULE,
        created_at=NOW,
    )


def post_task(url=POST_URL, post_id=POST_ID):
    return CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.POST,
        board="Stock",
        url=url,
        post_id=post_id,
        reason=CrawlReason.RECRAWL,
        created_at=NOW,
    )


@pytest.fixture
def producer():
    return FakeProducer()


@pytest.fixture
def cache():
    return ListPushCache()


@pytest.fixture
def handler(fetcher, producer, cache):
    json_producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer)
    return CrawlHandler(fetcher, json_producer, cache, clock=lambda: NOW)


def sent(producer, topic):
    return [m for m in producer.produced if m["topic"] == topic]


def seed_cache(cache, post_id, push):
    url = f"https://www.ptt.cc/bbs/Stock/{post_id.split('.', 1)[1]}.html"
    cache.remember(ListEntry(post_id, url, "t", "a", push, False))


# ---------- list 任務 ----------
def test_list_task_fetches_unseen_posts_and_publishes(handler, fetcher, producer):
    handler([list_task()])

    # list_stock.html：3 篇有連結的文章 + 1 篇刪除文
    assert len(fetcher.post_requests()) == 3
    assert len(sent(producer, names.RAW_POSTS)) == 3
    assert len(sent(producer, names.RAW_HTML)) == 3


def test_list_task_skips_posts_with_unchanged_push_count(handler, fetcher, cache):
    seed_cache(cache, POST_ID, 10)  # list_stock.html 上這篇顯示 10

    handler([list_task()])

    assert POST_URL not in fetcher.post_requests()
    assert len(fetcher.post_requests()) == 2


def test_list_task_skips_deleted_entries(handler, fetcher, cache):
    handler([list_task()])

    assert all("本文已被刪除" not in u for u in fetcher.requested)
    assert len(cache) == 3


def test_list_task_follows_prev_page_when_all_entries_new(handler, fetcher, cache):
    fetcher.pages[PREV_URL] = read_fixture("list_first_page.html")
    seed_cache(cache, "Stock.M.1.A.001", 1)  # 快取非空，但與第一頁都無關

    handler([list_task()])

    assert fetcher.list_requests() == [INDEX_URL, PREV_URL]
    assert len(fetcher.post_requests()) == 3 + 20


def test_list_task_stops_at_max_pages(fetcher, producer, cache):
    fetcher.pages[PREV_URL] = read_fixture("list_first_page.html")
    seed_cache(cache, "Stock.M.1.A.001", 1)
    json_producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer)
    handler = CrawlHandler(fetcher, json_producer, cache, clock=lambda: NOW, max_list_pages=1)

    handler([list_task()])

    assert fetcher.list_requests() == [INDEX_URL]


def test_list_task_first_run_with_empty_cache_reads_one_page(handler, fetcher):
    fetcher.pages[PREV_URL] = read_fixture("list_first_page.html")

    handler([list_task()])

    assert fetcher.list_requests() == [INDEX_URL]


def test_list_task_parse_error_is_logged_and_skipped(handler, fetcher, producer):
    fetcher.pages[INDEX_URL] = read_fixture("over18.html")

    handler([list_task()])

    assert producer.produced == []
    assert fetcher.post_requests() == []


def test_list_task_non_200_is_skipped(handler, fetcher, producer):
    fetcher.status[INDEX_URL] = 404

    handler([list_task()])

    assert producer.produced == []


# ---------- post 任務 ----------
def test_post_task_publishes_raw_post_and_raw_html_keyed_by_post_id(handler, producer):
    handler([post_task()])

    [raw_post] = sent(producer, names.RAW_POSTS)
    [raw_html] = sent(producer, names.RAW_HTML)
    assert raw_post["key"] == raw_html["key"] == POST_ID.encode()
    post = RawPost.model_validate(json.loads(raw_post["value"]))
    assert (post.post_id, post.crawled_at, post.push_count) == (POST_ID, NOW, 9)


def test_post_task_404_publishes_deleted_post(handler, fetcher, producer):
    fetcher.status[POST_URL] = 404

    handler([post_task()])

    [raw_post] = sent(producer, names.RAW_POSTS)
    assert json.loads(raw_post["value"])["is_deleted"] is True
    assert sent(producer, names.RAW_HTML) == []


def test_post_task_parse_error_still_publishes_raw_html(handler, fetcher, producer):
    fetcher.pages[POST_URL] = read_fixture("over18.html")

    handler([post_task()])

    assert sent(producer, names.RAW_POSTS) == []
    assert len(sent(producer, names.RAW_HTML)) == 1


def test_post_task_fetch_error_is_skipped(handler, fetcher, producer):
    fetcher.errors[POST_URL] = FetchError("403")

    handler([post_task()])

    assert producer.produced == []


# ---------- 共通 ----------
def test_handler_flushes_producer_after_batch(handler, producer):
    handler([post_task()])

    assert producer._pending == []


def test_transient_fetch_error_propagates(handler, fetcher):
    fetcher.errors[POST_URL] = TransientError("503")

    with pytest.raises(TransientError):
        handler([post_task()])


def test_deleted_post_uses_filename_time_and_zero_counts():
    post = deleted_post(POST_ID, "Stock", POST_URL, uuid.uuid4(), NOW)

    assert post.is_deleted
    assert post.created_at == datetime.fromtimestamp(1791345103, UTC)
    assert (post.push_count, post.boo_count, post.comments) == (0, 0, [])

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from radar.collector.crawler import CrawlHandler, deleted_post
from radar.collector.fetch_cache import RecentFetches
from radar.collector.http import FetchError
from radar.collector.list_cache import ListPushCache
from radar.collector.parsers.ptt import ListEntry, post_id_from_url
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


def post_task(url=POST_URL, post_id=POST_ID, created_at=NOW):
    return CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.POST,
        board="Stock",
        url=url,
        post_id=post_id,
        reason=CrawlReason.RECRAWL,
        created_at=created_at,
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
    return CrawlHandler(fetcher, json_producer, cache, RecentFetches(), clock=lambda: NOW)


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
    handler = CrawlHandler(
        fetcher, json_producer, cache, RecentFetches(), clock=lambda: NOW, max_list_pages=1
    )

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


def test_list_task_post_fetch_error_is_refetched_on_next_poll(handler, fetcher, cache):
    # #33：新文章第一次抓取失敗後被記進快取，推文數沒變就永遠不再抓
    fetcher.errors[POST_URL] = FetchError("GET returned 520")
    handler([list_task()])
    del fetcher.errors[POST_URL]
    fetcher.requested.clear()

    handler([list_task()])

    assert fetcher.post_requests() == [POST_URL]
    assert POST_ID in cache


class FakeLog:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _add(self, level: str, msg: str, *args: object) -> None:
        self.records.append((level, msg % args if args else msg))

    def info(self, msg: str, *args: object) -> None:
        self._add("INFO", msg, *args)

    def warning(self, msg: str, *args: object) -> None:
        self._add("WARNING", msg, *args)

    def error(self, msg: str, *args: object) -> None:
        self._add("ERROR", msg, *args)

    def levels(self, *, skip_info: bool = True) -> list[str]:
        return [lv for lv, _ in self.records if not (skip_info and lv == "INFO")]


@pytest.fixture
def fake_log(monkeypatch) -> FakeLog:
    from radar.collector import crawler

    fake = FakeLog()
    monkeypatch.setattr(crawler, "log", fake)
    return fake


def test_list_task_post_fetch_error_gives_up_after_three_polls(handler, fetcher, cache, fake_log):
    fetcher.errors[POST_URL] = FetchError("GET returned 525")

    for _ in range(3):
        handler([list_task()])
    fetcher.requested.clear()
    handler([list_task()])

    assert POST_ID in cache
    assert POST_URL not in fetcher.post_requests()
    errors = [m for lv, m in fake_log.records if lv == "ERROR"]
    assert len(errors) == 1 and POST_ID in errors[0]


def test_list_task_success_after_failure_resets_failure_count(handler, fetcher, cache, fake_log):
    fetcher.errors[POST_URL] = FetchError("GET returned 520")
    handler([list_task()])
    handler([list_task()])  # 連續失敗 2 輪
    del fetcher.errors[POST_URL]
    handler([list_task()])  # 成功，計數歸零
    seed_cache(cache, POST_ID, 99)  # 推文數變了，之後的列表會再抓
    fetcher.errors[POST_URL] = FetchError("GET returned 520")

    handler([list_task()])
    handler([list_task()])  # 再失敗 2 輪，未達 3 輪

    assert handler._list_fetch_failures[POST_ID] == 2
    assert "ERROR" not in fake_log.levels()


def test_list_task_post_parse_error_is_remembered(handler, fetcher, cache):
    fetcher.pages[POST_URL] = "<html>not a post</html>"

    handler([list_task()])

    assert POST_ID in cache


def test_list_task_counts_only_published_posts(handler, fetcher):
    fetcher.errors[POST_URL] = FetchError("GET returned 520")

    assert handler.handle_list(list_task()) == 2


def test_list_failure_tracking_is_capped(fetcher, producer, cache, monkeypatch):
    json_producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer)
    handler = CrawlHandler(
        fetcher, json_producer, cache, RecentFetches(), clock=lambda: NOW,
        max_tracked_list_failures=2,
    )  # fmt: skip
    real_fetch = fetcher.fetch

    def fail_posts(url: str):
        if "/M." in url:
            raise FetchError(f"GET {url} returned 520")
        return real_fetch(url)

    monkeypatch.setattr(fetcher, "fetch", fail_posts)

    handler([list_task()])  # list_stock.html 有 3 篇新文章，全部失敗

    assert len(handler._list_fetch_failures) == 2


def test_post_fetch_error_logs_warning_not_error(handler, fetcher, fake_log):
    fetcher.errors[POST_URL] = FetchError("GET returned 520")

    handler([post_task()])

    assert fake_log.levels() == ["WARNING"]


def test_list_page_fetch_error_logs_warning(handler, fetcher, fake_log):
    fetcher.errors[INDEX_URL] = FetchError("GET returned 525")

    handler([list_task()])

    assert fake_log.levels() == ["WARNING"]


def test_failure_streak_logs_error_once_and_info_on_recovery(fetcher, producer, cache, fake_log):
    json_producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer)
    handler = CrawlHandler(
        fetcher, json_producer, cache, RecentFetches(), clock=lambda: NOW, failure_streak_alert=3
    )
    fetcher.errors[POST_URL] = FetchError("GET returned 520")
    for _ in range(4):
        handler([post_task()])
    del fetcher.errors[POST_URL]

    handler([post_task(created_at=NOW + timedelta(seconds=1))])

    assert [lv for lv, _ in fake_log.records].count("ERROR") == 1
    assert any(lv == "INFO" and "recovered after 4" in m for lv, m in fake_log.records)


def test_failure_streak_resets_on_success_without_alert(handler, fetcher, fake_log):
    fetcher.errors[POST_URL] = FetchError("GET returned 520")
    handler([post_task()])
    del fetcher.errors[POST_URL]

    handler([post_task(created_at=NOW + timedelta(seconds=1))])

    assert "ERROR" not in fake_log.levels()
    assert handler._failure_streak == 0


def test_transient_give_up_counts_toward_failure_streak(fetcher, producer, cache, fake_log):
    json_producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer)
    handler = CrawlHandler(
        fetcher, json_producer, cache, RecentFetches(), clock=lambda: NOW,
        max_transient_attempts=1, failure_streak_alert=1,
    )  # fmt: skip
    fetcher.errors[POST_URL] = TransientError("timeout")

    handler([post_task()])

    assert [lv for lv, _ in fake_log.records].count("ERROR") == 1


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


# --- #11：同一網址連續暫時性失敗的上限 ---


def retry_until_done(handler, task, attempts=10):
    """模擬 BatchConsumer 對同一批的重試；回傳拋出 TransientError 的次數。"""
    for failures in range(attempts):
        try:
            handler([task])
            return failures
        except TransientError:
            continue
    raise AssertionError("handler kept failing")


def test_post_timeout_below_cap_raises_transient(handler, fetcher):
    fetcher.errors[POST_URL] = TransientError("timeout")

    for _ in range(4):
        with pytest.raises(TransientError):
            handler([post_task()])


def test_post_timeout_fifth_time_skips_post_without_raising(handler, fetcher, producer):
    fetcher.errors[POST_URL] = TransientError("timeout")

    assert retry_until_done(handler, post_task()) == 4
    assert len(fetcher.post_requests()) == 5
    assert producer.produced == []


def test_transient_attempts_reset_after_success(handler, fetcher, producer):
    fetcher.errors[POST_URL] = TransientError("timeout")
    for _ in range(4):
        with pytest.raises(TransientError):
            handler([post_task()])
    del fetcher.errors[POST_URL]
    handler([post_task()])
    fetcher.errors[POST_URL] = TransientError("timeout")

    # 成功後重新計數，下一批又可以重試 4 次
    assert retry_until_done(handler, post_task()) == 4


def test_transient_attempts_counted_per_url(handler, fetcher):
    other = "https://www.ptt.cc/bbs/Stock/M.1791345104.A.E42.html"
    fetcher.errors[POST_URL] = TransientError("timeout")
    fetcher.errors[other] = TransientError("timeout")
    for _ in range(4):
        with pytest.raises(TransientError):
            handler([post_task()])

    with pytest.raises(TransientError):
        handler([post_task(other, "Stock.M.1791345104.A.E42")])


def test_list_page_timeout_fifth_time_skips_list(handler, fetcher, producer):
    fetcher.errors[INDEX_URL] = TransientError("timeout")

    assert retry_until_done(handler, list_task()) == 4
    assert fetcher.list_requests() == [INDEX_URL] * 5
    assert producer.produced == []


# ---------- 略過重複的重爬任務（開發規格 7.12） ----------
LATER = NOW + timedelta(minutes=5)


@pytest.fixture
def recent():
    return RecentFetches()


@pytest.fixture
def later_handler(fetcher, producer, cache, recent):
    """抓取時間是 LATER，晚於 NOW 派發的任務。"""
    json_producer = JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer)
    return CrawlHandler(fetcher, json_producer, cache, recent, clock=lambda: LATER)


def test_post_task_already_fetched_after_dispatch_is_skipped_without_request(
    later_handler, fetcher, producer, recent
):
    recent.remember(POST_ID, NOW + timedelta(minutes=1))

    assert later_handler.handle_post(post_task(created_at=NOW)) is False
    assert fetcher.requested == []
    assert producer.produced == []


def test_post_task_fetched_before_dispatch_is_fetched_again(later_handler, fetcher, recent):
    recent.remember(POST_ID, NOW - timedelta(minutes=1))

    assert later_handler.handle_post(post_task(created_at=NOW)) is True
    assert fetcher.post_requests() == [POST_URL]


def test_duplicate_post_tasks_in_queue_fetch_once(later_handler, fetcher, producer):
    later_handler([post_task(created_at=NOW)])
    later_handler([post_task(created_at=NOW + timedelta(minutes=2))])

    assert fetcher.post_requests() == [POST_URL]
    assert len(sent(producer, names.RAW_POSTS)) == 1


def test_post_fetched_via_list_task_skips_older_recrawl_task(later_handler, fetcher):
    later_handler([list_task()])
    url = fetcher.post_requests()[0]
    fetched = len(fetcher.post_requests())

    later_handler([post_task(url=url, post_id=post_id_from_url(url), created_at=NOW)])

    assert len(fetcher.post_requests()) == fetched


def test_post_404_is_remembered_as_fetched(later_handler, fetcher):
    fetcher.status[POST_URL] = 404

    later_handler([post_task(created_at=NOW)])
    later_handler([post_task(created_at=NOW)])

    assert fetcher.post_requests() == [POST_URL]


def test_post_parse_error_is_remembered_as_fetched(later_handler, fetcher):
    fetcher.pages[POST_URL] = read_fixture("over18.html")

    later_handler([post_task(created_at=NOW)])
    later_handler([post_task(created_at=NOW)])

    assert fetcher.post_requests() == [POST_URL]


def test_post_fetch_error_is_not_remembered(later_handler, fetcher, recent):
    fetcher.errors[POST_URL] = FetchError("403")

    later_handler([post_task(created_at=NOW)])

    assert not recent.fetched_since(POST_ID, NOW)


def test_transient_error_is_not_remembered(later_handler, fetcher):
    fetcher.errors[POST_URL] = TransientError("503")
    with pytest.raises(TransientError):
        later_handler([post_task(created_at=NOW)])
    del fetcher.errors[POST_URL]

    later_handler([post_task(created_at=NOW)])

    assert fetcher.post_requests() == [POST_URL, POST_URL]

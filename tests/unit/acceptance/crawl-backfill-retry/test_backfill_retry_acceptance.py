"""開發規格 7.28 A（crawl-backfill-retry）：補抓途中 TransientError 整批重試後續抓鏈不斷。"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from tests.unit.collector.conftest import FakeFetcher
from tests.unit.common.kafka.fakes import FakeProducer

from radar.collector.crawler import CrawlHandler
from radar.collector.fetch_cache import RecentFetches
from radar.collector.list_cache import ListPushCache
from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names
from radar.common.kafka.consumer import TransientError
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import CrawlTask
from radar.common.settings import KafkaSettings

NOW = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
BASE = 1_790_000_000  # 第 p 頁文章的 epoch ＝ BASE + p * 1000 + 序號 * 10
ROOT = "https://www.ptt.cc/bbs/Stock"
LONG_AGO = datetime.fromtimestamp(BASE, UTC) - timedelta(days=1)


def page_url(p: int) -> str:
    return f"{ROOT}/index{p}.html"


def epoch(p: int, j: int = 0) -> int:
    return BASE + p * 1000 + j * 10


def post_url(p: int, j: int = 0) -> str:
    return f"{ROOT}/M.{epoch(p, j)}.A.{j:03X}.html"


def list_html(p: int, per_page: int) -> str:
    prev = (
        f'<a class="btn wide" href="/bbs/Stock/index{p - 1}.html">&lsaquo; 上頁</a>'
        if p > 1
        else '<a class="btn wide disabled">&lsaquo; 上頁</a>'
    )
    rows = "".join(
        '<div class="r-ent"><div class="nrec"><span class="hl f2">1</span></div>'
        f'<div class="title"><a href="/bbs/Stock/M.{epoch(p, j)}.A.{j:03X}.html">t{p}-{j}</a>'
        '</div><div class="meta"><div class="author">u</div></div></div>'
        for j in range(per_page)
    )
    return (
        '<html><body><div class="btn-group btn-group-paging">'
        f'<a class="btn wide" href="/bbs/Stock/index1.html">最舊</a>{prev}</div>'
        f'<div class="r-list-container">{rows}</div></body></html>'
    )


def make_board(fetcher: FakeFetcher, pages: int, per_page: int = 2) -> str:
    fetcher.pages.clear()
    for p in range(1, pages + 1):
        fetcher.pages[page_url(p)] = list_html(p, per_page)
    fetcher.pages[f"{ROOT}/index.html"] = list_html(pages, per_page)
    return f"{ROOT}/index.html"


def task(
    url: str,
    *,
    since: datetime | None = LONG_AGO,
    reason: CrawlReason = CrawlReason.SCHEDULE,
    depth: int = 0,
    created_at: datetime = NOW,
) -> CrawlTask:
    return CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.LIST,
        board="Stock",
        url=url,
        reason=reason,
        since=since,
        backfill_depth=depth,
        created_at=created_at,
    )


class Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def build(fetcher, producer, clock=None) -> CrawlHandler:
    return CrawlHandler(
        fetcher,
        JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer),
        ListPushCache(),
        RecentFetches(),
        clock=clock or Clock(),
    )


def follow_ups(producer: FakeProducer) -> list[CrawlTask]:
    return [
        CrawlTask.model_validate_json(m["value"])
        for m in producer.produced
        if m["topic"] == names.CRAWL_TASKS
    ]


def published(producer: FakeProducer) -> set[str]:
    return {m["key"].decode() for m in producer.produced if m["topic"] == names.RAW_POSTS}


def deliver(handler, t: CrawlTask, fetcher: FakeFetcher) -> int:
    """模擬 BatchConsumer：TransientError 就整批重試（暫時性錯誤只發生一次）。回傳嘗試次數。"""
    attempts = 0
    while True:
        attempts += 1
        try:
            handler([t])
            return attempts
        except TransientError:
            fetcher.errors.clear()
            assert attempts < 10


def run_chain(handler, producer, first: CrawlTask, fetcher: FakeFetcher) -> list[CrawlTask]:
    seen = 0
    queue = [first]
    out: list[CrawlTask] = []
    while queue:
        deliver(handler, queue.pop(0), fetcher)
        new = follow_ups(producer)[seen:]
        seen += len(new)
        out.extend(new)
        queue.extend(new)
    return out


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def producer() -> FakeProducer:
    return FakeProducer()


# ---------- 同一任務重試不被當積壓略過 ----------
def test_retried_schedule_task_after_transient_error_is_not_skipped(fetcher, producer):
    index = make_board(fetcher, 8)
    fetcher.errors[post_url(7, 0)] = TransientError("429")
    handler = build(fetcher, producer)

    attempts = deliver(handler, task(index), fetcher)

    assert attempts == 2
    # 重試真的重讀了列表，並送出續抓任務
    assert fetcher.list_requests().count(index) == 2
    [cont] = follow_ups(producer)
    assert cont.reason is CrawlReason.BACKFILL
    assert cont.url == page_url(5)


def test_failed_task_does_not_record_start_time(fetcher, producer):
    index = make_board(fetcher, 3)
    fetcher.errors[post_url(3, 0)] = TransientError("timeout")
    handler = build(fetcher, producer)

    with pytest.raises(TransientError):
        handler([task(index, since=None, created_at=NOW)])
    fetcher.errors.clear()
    fetcher.requested.clear()

    # 失敗那次沒有記開始時間，所以較早建立的任務不被略過
    handler([task(index, since=None, created_at=NOW - timedelta(minutes=1))])

    assert fetcher.list_requests() == [index]


def test_recorded_start_time_is_start_not_completion_time(fetcher, producer):
    index = make_board(fetcher, 1)
    clock = Clock(NOW)
    handler = build(fetcher, producer, clock)
    original = fetcher.fetch

    def slow_fetch(url):
        clock.now = NOW + timedelta(minutes=10)
        return original(url)

    fetcher.fetch = slow_fetch
    handler([task(index, since=None, created_at=NOW)])
    fetcher.requested.clear()

    # 處理期間（開始～結束）建立的任務不可被略過
    handler([task(index, since=None, created_at=NOW + timedelta(minutes=5))])

    assert fetcher.list_requests() == [index]


def test_completed_task_still_skips_older_schedule_task(fetcher, producer):
    index = make_board(fetcher, 1)
    handler = build(fetcher, producer)
    handler([task(index, since=None, created_at=NOW)])
    fetcher.requested.clear()

    handler([task(index, since=None, created_at=NOW - timedelta(seconds=1))])

    assert fetcher.requested == []


# ---------- 續抓鏈在重試後接著補到 since ----------
def test_chain_completes_when_transient_error_hits_first_task(fetcher, producer):
    index = make_board(fetcher, 8)
    fetcher.errors[post_url(6, 1)] = TransientError("503")
    handler = build(fetcher, producer)

    conts = run_chain(handler, producer, task(index), fetcher)

    assert [(c.url, c.backfill_depth) for c in conts] == [(page_url(5), 3), (page_url(2), 6)]
    assert published(producer) == {
        f"Stock.M.{epoch(p, j)}.A.{j:03X}" for p in range(1, 9) for j in (0, 1)
    }


def test_continuation_retry_rereads_first_page_and_keeps_going(fetcher, producer):
    index = make_board(fetcher, 8)
    handler = build(fetcher, producer)
    first = task(index)
    deliver(handler, first, fetcher)
    [cont] = follow_ups(producer)
    # 續抓任務的第 4 頁內頁出錯；重試時第 5 頁文章都已在快取
    fetcher.errors[post_url(4, 0)] = TransientError("429")
    fetcher.requested.clear()

    attempts = deliver(handler, cont, fetcher)

    assert attempts == 2
    assert fetcher.list_requests()[-3:] == [page_url(5), page_url(4), page_url(3)]
    nxt = follow_ups(producer)[-1]
    assert nxt.url == page_url(2)
    assert nxt.backfill_depth == 6


def test_chain_reaches_since_after_retry_in_last_continuation(fetcher, producer):
    index = make_board(fetcher, 8)
    fetcher.errors[post_url(2, 0)] = TransientError("timeout")
    handler = build(fetcher, producer)

    conts = run_chain(handler, producer, task(index), fetcher)

    assert conts[-1].url == page_url(2)
    assert page_url(1) in fetcher.list_requests()
    assert post_url(1, 1) in fetcher.post_requests()


def test_chain_stops_at_since_after_retry(fetcher, producer):
    index = make_board(fetcher, 8)
    fetcher.errors[post_url(7, 0)] = TransientError("429")
    handler = build(fetcher, producer)
    since = datetime.fromtimestamp(epoch(4), UTC) + timedelta(seconds=1)

    conts = run_chain(handler, producer, task(index, since=since), fetcher)

    # 讀到第 4 頁（最舊文章早於 since）為止，不再往前
    assert [c.url for c in conts] == [page_url(5)]
    assert page_url(3) not in fetcher.list_requests()


# ---------- since 非 null 時快取不單獨使翻頁停止 ----------
def test_since_set_and_fully_cached_pages_still_follow_prev_until_since(fetcher, producer):
    index = make_board(fetcher, 3)
    handler = build(fetcher, producer)
    handler([task(index, since=None)])  # 第一頁全進快取
    fetcher.requested.clear()

    handler([task(index, since=LONG_AGO)])

    assert fetcher.list_requests() == [index, page_url(2), page_url(1)]


def test_since_null_still_reads_one_page_even_when_cache_empty(fetcher, producer):
    index = make_board(fetcher, 3)

    build(fetcher, producer)([task(index, since=None)])

    assert fetcher.list_requests() == [index]

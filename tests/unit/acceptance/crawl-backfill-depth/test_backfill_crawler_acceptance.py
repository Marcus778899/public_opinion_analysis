"""開發規格 7.28 A：翻頁規則、續抓任務、80 頁上限、略過積壓的列表任務。"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from tests.unit.collector.conftest import FakeFetcher
from tests.unit.common.kafka.fakes import FakeProducer

from radar.collector import crawler
from radar.collector.crawler import CrawlHandler
from radar.collector.fetch_cache import RecentFetches
from radar.collector.list_cache import ListPushCache
from radar.collector.parsers.ptt import ListEntry
from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.schemas import CrawlTask
from radar.common.settings import KafkaSettings

NOW = datetime(2026, 10, 29, 6, 0, tzinfo=UTC)
BASE = 1_790_000_000  # 第 p 頁文章的 epoch ＝ BASE + p * 1000 + 序號 * 10
ROOT = "https://www.ptt.cc/bbs/Stock"


def page_url(p: int) -> str:
    return f"{ROOT}/index{p}.html"


def epoch(p: int, j: int = 0) -> int:
    return BASE + p * 1000 + j * 10


def at(p: int, j: int = 0) -> datetime:
    return datetime.fromtimestamp(epoch(p, j), UTC)


def post_id(p: int, j: int = 0) -> str:
    return f"Stock.M.{epoch(p, j)}.A.{j:03X}"


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
    """建立 1..pages 頁；回傳最新頁（index.html）的網址。"""
    fetcher.pages.clear()
    for p in range(1, pages + 1):
        fetcher.pages[page_url(p)] = list_html(p, per_page)
    fetcher.pages[f"{ROOT}/index.html"] = list_html(pages, per_page)
    return f"{ROOT}/index.html"


def task(
    url: str,
    *,
    since: datetime | None = None,
    reason: CrawlReason = CrawlReason.SCHEDULE,
    depth: int = 0,
    created_at: datetime = NOW,
    board: str = "Stock",
) -> CrawlTask:
    return CrawlTask(
        task_id=uuid.uuid4(),
        type=CrawlTaskType.LIST,
        board=board,
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


def build(fetcher, producer, cache=None, clock=None, **kwargs) -> CrawlHandler:
    return CrawlHandler(
        fetcher,
        JsonProducer(KafkaSettings(bootstrap_servers="x"), producer=producer),
        cache if cache is not None else ListPushCache(),
        RecentFetches(),
        clock=clock or Clock(),
        **kwargs,
    )


def follow_ups(producer: FakeProducer) -> list[CrawlTask]:
    return [
        CrawlTask.model_validate_json(m["value"])
        for m in producer.produced
        if m["topic"] == names.CRAWL_TASKS
    ]


def run_chain(handler, producer, first: CrawlTask, limit: int = 200) -> list[CrawlTask]:
    """依序處理任務與其送出的續抓任務；回傳所有續抓任務。"""
    seen = 0
    queue = [first]
    out: list[CrawlTask] = []
    while queue and limit:
        limit -= 1
        handler([queue.pop(0)])
        new = follow_ups(producer)[seen:]
        seen += len(new)
        out.extend(new)
        queue.extend(new)
    return out


def seed(cache: ListPushCache, pid: str) -> None:
    cache.remember(ListEntry(pid, f"{ROOT}/{pid.split('.', 1)[1]}.html", "t", "a", 1, False))


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()


@pytest.fixture
def producer() -> FakeProducer:
    return FakeProducer()


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

    def errors(self) -> list[str]:
        return [m for lv, m in self.records if lv == "ERROR"]


@pytest.fixture
def fake_log(monkeypatch) -> FakeLog:
    fake = FakeLog()
    monkeypatch.setattr(crawler, "log", fake)
    return fake


# ---------- 翻頁規則 ----------
def test_since_null_reads_only_first_page_even_with_empty_cache(fetcher, producer):
    index = make_board(fetcher, 5)

    build(fetcher, producer)([task(index, since=None)])

    assert fetcher.list_requests() == [index]
    assert follow_ups(producer) == []


def test_since_set_follows_prev_pages_until_since(fetcher, producer):
    index = make_board(fetcher, 5)

    # 第 3 頁最舊文章（序號 0）epoch ＝ BASE+3000，晚於 since 才會繼續往前
    build(fetcher, producer)([task(index, since=at(3) - timedelta(seconds=1))])

    assert fetcher.list_requests() == [index, page_url(4), page_url(3)]
    assert len(fetcher.post_requests()) == 6


def test_stops_when_oldest_post_is_not_later_than_since(fetcher, producer):
    index = make_board(fetcher, 5)

    build(fetcher, producer)([task(index, since=at(4) + timedelta(seconds=1))])

    # 第 4 頁最舊文章早於 since，讀完第 4 頁就停
    assert fetcher.list_requests() == [index, page_url(4)]
    assert follow_ups(producer) == []


def test_oldest_post_equal_to_since_stops(fetcher, producer):
    index = make_board(fetcher, 5)

    build(fetcher, producer)([task(index, since=at(4))])

    assert fetcher.list_requests() == [index, page_url(4)]


def test_cached_post_on_page_does_not_stop_paging_when_since_set(fetcher, producer):
    # crawl-backfill-retry：since 不是 null 時，快取文章不單獨使翻頁停止
    index = make_board(fetcher, 5)
    cache = ListPushCache()
    seed(cache, post_id(4, 1))

    build(fetcher, producer, cache)([task(index, since=at(1) - timedelta(days=1))])

    assert fetcher.list_requests() == [index, page_url(4), page_url(3)]
    [cont] = follow_ups(producer)
    assert cont.url == page_url(2)


def test_normal_poll_with_seen_first_page_reads_one_page(fetcher, producer):
    index = make_board(fetcher, 5)
    cache = ListPushCache()
    seed(cache, post_id(5, 0))

    # 正常運作時 since 約等於 PG 最新文章：第一頁最舊文章已不晚於 since，讀一頁就停
    build(fetcher, producer, cache)([task(index, since=at(5))])

    assert fetcher.list_requests() == [index]
    assert follow_ups(producer) == []


def test_stops_at_first_page_without_prev_link(fetcher, producer):
    index = make_board(fetcher, 2)

    build(fetcher, producer)([task(index, since=at(1) - timedelta(days=1))])

    assert fetcher.list_requests() == [index, page_url(1)]
    assert follow_ups(producer) == []


def test_all_posts_in_read_pages_are_published(fetcher, producer):
    index = make_board(fetcher, 3)

    build(fetcher, producer)([task(index, since=at(1) - timedelta(days=1))])

    sent = {m["key"].decode() for m in producer.produced if m["topic"] == names.RAW_POSTS}
    assert sent == {post_id(p, j) for p in (1, 2, 3) for j in (0, 1)}


# ---------- 續抓任務 ----------
def test_three_pages_then_sends_continuation_task(fetcher, producer):
    index = make_board(fetcher, 8)
    since = at(1) - timedelta(days=1)

    build(fetcher, producer)([task(index, since=since)])

    assert fetcher.list_requests() == [index, page_url(7), page_url(6)]
    [cont] = follow_ups(producer)
    assert cont.type is CrawlTaskType.LIST
    assert cont.reason is CrawlReason.BACKFILL
    assert cont.board == "Stock"
    assert cont.url == page_url(5)
    assert cont.since == since
    assert cont.backfill_depth == 3
    assert cont.post_id is None


def test_continuation_task_is_keyed_by_board_without_partition(fetcher, producer):
    index = make_board(fetcher, 8)

    build(fetcher, producer)([task(index, since=at(1) - timedelta(days=1))])

    [message] = [m for m in producer.produced if m["topic"] == names.CRAWL_TASKS]
    assert message["key"] == b"Stock"
    assert "partition" not in message
    assert json.loads(message["value"])["reason"] == "backfill"


def test_continuation_is_flushed_before_handler_returns(fetcher, producer):
    index = make_board(fetcher, 8)

    build(fetcher, producer)([task(index, since=at(1) - timedelta(days=1))])

    assert producer._pending == []


def test_continuation_created_at_is_clock_time(fetcher, producer):
    index = make_board(fetcher, 8)

    build(fetcher, producer)([task(index, since=at(1) - timedelta(days=1))])

    [cont] = follow_ups(producer)
    assert cont.created_at == NOW


def test_continuation_task_resumes_and_chain_reads_every_page(fetcher, producer):
    index = make_board(fetcher, 8)
    handler = build(fetcher, producer)

    conts = run_chain(handler, producer, task(index, since=at(1) - timedelta(days=1)))

    assert [(c.url, c.backfill_depth) for c in conts] == [(page_url(5), 3), (page_url(2), 6)]
    assert fetcher.list_requests() == [index] + [page_url(p) for p in range(7, 0, -1)]
    sent = {m["key"].decode() for m in producer.produced if m["topic"] == names.RAW_POSTS}
    assert len(sent) == 16


def test_continuation_stops_when_since_reached_mid_chain(fetcher, producer):
    index = make_board(fetcher, 8)
    handler = build(fetcher, producer)

    conts = run_chain(handler, producer, task(index, since=at(4) + timedelta(seconds=1)))

    # 第 7、6 頁後送續抓；續抓讀第 5、4 頁，第 4 頁最舊早於 since → 結束
    assert [c.url for c in conts] == [page_url(5)]
    assert fetcher.list_requests()[-1] == page_url(4)


def test_backfill_task_continues_past_cached_post(fetcher, producer):
    make_board(fetcher, 8)
    cache = ListPushCache()
    seed(cache, post_id(4, 1))
    since = at(1) - timedelta(days=1)

    build(fetcher, producer, cache)(
        [task(page_url(5), since=since, reason=CrawlReason.BACKFILL, depth=3)]
    )

    assert fetcher.list_requests() == [page_url(5), page_url(4), page_url(3)]
    [cont] = follow_ups(producer)
    assert cont.url == page_url(2)
    assert cont.backfill_depth == 6


# ---------- 上限 ----------
def test_chain_stops_at_max_backfill_pages_and_logs_error(fetcher, producer, fake_log):
    index = make_board(fetcher, 10)
    handler = build(fetcher, producer, max_backfill_pages=6)
    since = at(1) - timedelta(days=1)

    conts = run_chain(handler, producer, task(index, since=since))

    assert len(fetcher.list_requests()) == 6
    assert [c.backfill_depth for c in conts] == [3]
    [error] = fake_log.errors()
    assert "Stock" in error


def test_cap_not_multiple_of_page_budget_reads_only_remaining_pages(fetcher, producer, fake_log):
    index = make_board(fetcher, 10)
    handler = build(fetcher, producer, max_backfill_pages=4)

    conts = run_chain(handler, producer, task(index, since=at(1) - timedelta(days=1)))

    assert len(fetcher.list_requests()) == 4
    assert [c.backfill_depth for c in conts] == [3]
    assert len(fake_log.errors()) == 1


def test_continuation_at_cap_reads_nothing_more_than_cap(fetcher, producer, fake_log):
    make_board(fetcher, 10)
    handler = build(fetcher, producer, max_backfill_pages=6)

    handler(
        [
            task(
                page_url(6),
                since=at(1) - timedelta(days=1),
                reason=CrawlReason.BACKFILL,
                depth=3,
            )
        ]
    )

    assert fetcher.list_requests() == [page_url(6), page_url(5), page_url(4)]
    assert follow_ups(producer) == []
    assert len(fake_log.errors()) == 1


def test_default_cap_is_80_pages(fetcher, producer, fake_log):
    index = make_board(fetcher, 100, per_page=1)
    handler = build(fetcher, producer)

    conts = run_chain(handler, producer, task(index, since=at(1) - timedelta(days=1)))

    assert len(fetcher.list_requests()) == 80
    assert conts[-1].backfill_depth == 78
    assert len(fake_log.errors()) == 1


def test_natural_end_before_cap_does_not_log_error(fetcher, producer, fake_log):
    index = make_board(fetcher, 3)

    build(fetcher, producer, max_backfill_pages=3)([task(index, since=at(1) - timedelta(days=1))])

    assert fake_log.errors() == []


# ---------- 略過積壓的列表任務 ----------
def test_older_schedule_task_is_skipped_after_newer_one_started(fetcher, producer):
    index = make_board(fetcher, 1)
    handler = build(fetcher, producer)
    handler([task(index, created_at=NOW - timedelta(minutes=1))])
    fetcher.requested.clear()

    handler([task(index, created_at=NOW - timedelta(seconds=30))])

    assert fetcher.requested == []


def test_task_created_after_last_start_is_processed(fetcher, producer):
    index = make_board(fetcher, 1)
    handler = build(fetcher, producer)
    handler([task(index, created_at=NOW - timedelta(minutes=1))])
    fetcher.requested.clear()

    handler([task(index, created_at=NOW + timedelta(seconds=1))])

    assert fetcher.list_requests() == [index]


def test_first_list_task_after_restart_is_never_skipped(fetcher, producer):
    index = make_board(fetcher, 1)

    build(fetcher, producer)([task(index, created_at=NOW - timedelta(hours=10))])

    assert fetcher.list_requests() == [index]


def test_skip_is_tracked_per_board(fetcher, producer):
    index = make_board(fetcher, 1)
    handler = build(fetcher, producer)
    handler([task(index, created_at=NOW)])
    fetcher.requested.clear()

    handler([task(index, created_at=NOW - timedelta(minutes=5), board="HatePolitics")])

    assert fetcher.list_requests() == [index]


def test_backfill_task_is_never_skipped(fetcher, producer):
    index = make_board(fetcher, 6)
    handler = build(fetcher, producer)
    handler([task(index, created_at=NOW)])
    fetcher.requested.clear()

    handler(
        [
            task(
                page_url(3),
                since=at(1) - timedelta(days=1),
                reason=CrawlReason.BACKFILL,
                depth=3,
                created_at=NOW - timedelta(hours=1),
            )
        ]
    )

    assert fetcher.list_requests()[0] == page_url(3)


def test_skipped_task_sends_nothing(fetcher, producer):
    index = make_board(fetcher, 8)
    handler = build(fetcher, producer)
    handler([task(index, created_at=NOW)])
    before = len(producer.produced)

    handler([task(index, since=at(1) - timedelta(days=1), created_at=NOW - timedelta(minutes=2))])

    assert len(producer.produced) == before


def test_skip_uses_start_time_of_latest_processed_task(fetcher, producer):
    index = make_board(fetcher, 1)
    clock = Clock(NOW)
    handler = build(fetcher, producer, clock=clock)
    handler([task(index, created_at=NOW)])
    clock.now = NOW + timedelta(minutes=10)
    handler([task(index, created_at=NOW + timedelta(minutes=10))])
    fetcher.requested.clear()

    # 比第二次開始時間早 5 分鐘建立：即使晚於第一次，也要略過
    handler([task(index, created_at=NOW + timedelta(minutes=5))])

    assert fetcher.requested == []

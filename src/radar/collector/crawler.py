"""爬蟲：消費 crawl.tasks，抓 PTT 頁面，寫入 raw.posts 與 raw.html。不碰 PG（設計文件 4.6）。"""

from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import ValidationError

from radar.collector.fetch_cache import RecentFetches
from radar.collector.http import FetchError, FetchResult, PttClient, PttFetcher
from radar.collector.list_cache import ListPushCache
from radar.collector.parsers.ptt import (
    ListEntry,
    ListPage,
    ParseError,
    parse_list_page,
    parse_post_page,
    post_id_from_url,
)
from radar.collector.parsers.ptt_time import created_at_from_filename
from radar.common.enums import CrawlReason, CrawlTaskType
from radar.common.ids import split_post_id
from radar.common.kafka import names
from radar.common.kafka.consumer import BatchConsumer, TransientError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.rate_limit import RateLimiter
from radar.common.schemas import CrawlTask, RawHtml, RawPost
from radar.common.settings import CrawlerSettings, get_kafka_settings


class PostOutcome(StrEnum):
    PUBLISHED = "published"  # 含 404 的刪除快照
    UNPARSABLE = "unparsable"
    FETCH_FAILED = "fetch_failed"


class CrawlHandler:
    """BatchConsumer 的 handler；HTTP 暫時性錯誤以 TransientError 往外拋，讓整批重試。"""

    def __init__(
        self,
        fetcher: PttFetcher,
        producer: JsonProducer,
        cache: ListPushCache,
        recent: RecentFetches,
        *,
        clock: Callable[[], datetime],
        max_list_pages: int = 3,
        max_backfill_pages: int = 80,
        max_transient_attempts: int = 5,
        max_list_fetch_failures: int = 3,
        max_tracked_list_failures: int = 1_000,
        failure_streak_alert: int = 20,
    ) -> None:
        self._fetcher = fetcher
        self._producer = producer
        self._cache = cache
        self._recent = recent
        self._clock = clock
        self._max_list_pages = max_list_pages
        self._max_backfill_pages = max_backfill_pages
        # 各看板最近一次開始處理（非續抓）列表任務的時間；重啟後清空
        self._last_list_start: dict[str, datetime] = {}
        self._max_transient_attempts = max_transient_attempts
        # 各網址連續暫時性失敗的次數；成功或略過後移除
        self._transient_attempts: dict[str, int] = {}
        self._max_list_fetch_failures = max_list_fetch_failures
        self._max_tracked_list_failures = max_tracked_list_failures
        # 列表任務中抓取失敗、還沒記進快取的文章：post_id → 連續失敗輪數（#33）
        self._list_fetch_failures: OrderedDict[str, int] = OrderedDict()
        self._failure_streak_alert = failure_streak_alert
        # 不分網址的連續抓取失敗次數；達門檻代表 PTT 或 Cloudflare 長時間無法連線
        self._failure_streak = 0

    def __call__(self, tasks: list[CrawlTask]) -> None:
        for task in tasks:
            if task.type is CrawlTaskType.LIST:
                self.handle_list(task)
            else:
                self.handle_post(task)
        # 確保 commit 前訊息已落地
        self._producer.flush()
        # 計數只用在同一批的重試之間；整批成功後清掉，避免殘留
        self._transient_attempts.clear()

    def handle_list(self, task: CrawlTask) -> int:
        """回傳抓了幾篇內頁。翻頁規則見開發規格 7.28 A。

        一個任務最多讀 max_list_pages 頁，還要翻就送續抓任務；一條鏈最多 max_backfill_pages 頁。
        """
        if task.reason is not CrawlReason.BACKFILL:
            started = self._last_list_start.get(task.board)
            if started is not None and task.created_at < started:
                log.info("skip stale list task %s created at %s", task.board, task.created_at)
                return 0
            self._last_list_start[task.board] = self._clock()
        depth = task.backfill_depth
        read = 0
        fetched = 0
        url: str | None = task.url
        oldest: datetime | None = None
        while url is not None:
            if read >= self._max_list_pages or depth >= self._max_backfill_pages:
                break
            page = self._fetch_list(url, task.board)
            if page is None:
                url = None
                break
            depth += 1
            read += 1
            linked = [e for e in page.entries if e.post_id]
            all_new = bool(linked) and all(e.post_id not in self._cache for e in linked)
            for entry in page.entries:
                if entry.url and self._cache.should_fetch(entry):
                    outcome = self.fetch_and_publish_post(entry.url, task.board, task.task_id)
                    fetched += outcome is PostOutcome.PUBLISHED
                    if outcome is PostOutcome.FETCH_FAILED and self._retry_on_next_poll(entry):
                        continue
                    self._list_fetch_failures.pop(entry.post_id or "", None)
                self._cache.remember(entry)
            oldest = _oldest_created_at(linked)
            if (
                task.since is None
                or not all_new
                or oldest is None
                or oldest <= task.since
                or page.prev_page_url is None
            ):
                url = None
                break
            url = page.prev_page_url
        if url is not None and task.since is not None:
            self._continue_or_stop(task, url, depth, oldest)
        log.info("list %s done, fetched %d posts", task.board, fetched)
        return fetched

    def _continue_or_stop(
        self, task: CrawlTask, url: str, depth: int, oldest: datetime | None
    ) -> None:
        if depth >= self._max_backfill_pages:
            log.error(
                "backfill of %s stopped at %d pages; since=%s, oldest post read=%s",
                task.board,
                depth,
                task.since,
                oldest,
            )
            return
        follow_up = task.model_copy(
            update={
                "task_id": uuid4(),
                "url": url,
                "reason": CrawlReason.BACKFILL,
                "backfill_depth": depth,
                "created_at": self._clock(),
            }
        )
        self._producer.send(names.CRAWL_TASKS, follow_up.kafka_key(), follow_up)

    def handle_post(self, task: CrawlTask) -> bool:
        """派發後已抓過（積壓時的重複派發）就略過、回傳 False；否則抓取並回傳 True。"""
        post_id = post_id_from_url(task.url)
        if self._recent.fetched_since(post_id, task.created_at):
            log.info("skip duplicate post task %s dispatched at %s", post_id, task.created_at)
            return False
        self.fetch_and_publish_post(task.url, task.board, task.task_id)
        return True

    def _retry_on_next_poll(self, entry: ListEntry) -> bool:
        """新文章抓取失敗時不記進快取，讓下一輪列表再抓；連續失敗達上限就放棄（#33）。"""
        post_id = entry.post_id or ""
        failures = self._list_fetch_failures.pop(post_id, 0) + 1
        if failures >= self._max_list_fetch_failures:
            log.error(
                "give up post %s after %d failed list polls; it may never be fetched",
                post_id,
                failures,
            )
            return False
        self._list_fetch_failures[post_id] = failures
        while len(self._list_fetch_failures) > self._max_tracked_list_failures:
            self._list_fetch_failures.popitem(last=False)
        return True

    def fetch_and_publish_post(self, url: str, board: str, task_id: UUID) -> PostOutcome:
        """抓取失敗記 WARNING 回傳 FETCH_FAILED；解析失敗記 ERROR 回傳 UNPARSABLE。"""
        post_id = post_id_from_url(url)
        try:
            result = self._fetch(url)
        except FetchError as e:
            log.warning("skip post %s: %s", post_id, e)
            return PostOutcome.FETCH_FAILED
        crawled_at = self._clock()
        # 404、解析失敗也算抓過：再抓一次結果相同
        self._recent.remember(post_id, crawled_at)
        if result.status == 404:
            self._producer.send(
                names.RAW_POSTS, post_id, deleted_post(post_id, board, url, task_id, crawled_at)
            )
            return PostOutcome.PUBLISHED
        html = RawHtml(post_id=post_id, url=url, crawled_at=crawled_at, html=result.html)
        self._producer.send(names.RAW_HTML, post_id, html)
        try:
            post = parse_post_page(
                result.html, board=board, url=url, crawled_at=crawled_at, task_id=task_id
            )
        except (ParseError, ValidationError) as e:
            # raw.html 已送出，修好 parser 後可重新解析
            log.error("parse failed for %s: %s", post_id, e)
            return PostOutcome.UNPARSABLE
        self._producer.send(names.RAW_POSTS, post_id, post)
        return PostOutcome.PUBLISHED

    def _fetch(self, url: str) -> FetchResult:
        """同一網址連續 TransientError 達上限就改拋 FetchError（略過），避免卡住 partition。"""
        try:
            result = self._fetcher.fetch(url)
        except TransientError as e:
            attempts = self._transient_attempts.get(url, 0) + 1
            if attempts >= self._max_transient_attempts:
                self._transient_attempts.pop(url, None)
                self._record_failure()
                raise FetchError(f"{e} (gave up after {attempts} attempts)") from e
            self._transient_attempts[url] = attempts
            raise
        except FetchError:
            self._record_failure()
            raise
        self._transient_attempts.pop(url, None)
        self._record_success()
        return result

    def _record_failure(self) -> None:
        self._failure_streak += 1
        if self._failure_streak == self._failure_streak_alert:
            log.error("%d fetches failed in a row; PTT may be unreachable", self._failure_streak)

    def _record_success(self) -> None:
        if self._failure_streak >= self._failure_streak_alert:
            log.info("fetch recovered after %d failures in a row", self._failure_streak)
        self._failure_streak = 0

    def _fetch_list(self, url: str, board: str) -> ListPage | None:
        try:
            result = self._fetch(url)
            if result.status != 200:
                raise FetchError(f"list page {url} returned {result.status}")
            return parse_list_page(result.html, board)
        except (FetchError, ParseError) as e:
            # 不重試，避免卡住 partition；下一輪輪詢會再試
            log.warning("skip list %s: %s", url, e)
            return None


def _oldest_created_at(entries: list[ListEntry]) -> datetime | None:
    times = []
    for e in entries:
        try:
            times.append(created_at_from_filename(split_post_id(e.post_id or "")[1]))
        except ValueError:
            continue
    return min(times) if times else None


def deleted_post(
    post_id: str, board: str, url: str, task_id: UUID, crawled_at: datetime
) -> RawPost:
    """文章頁 404 時送出的快照；created_at 由檔名 epoch 推算，ingest 只據此標記 is_deleted。"""
    return RawPost(
        task_id=task_id,
        post_id=post_id,
        board=board,
        url=url,
        author=None,
        title=None,
        content=None,
        created_at=created_at_from_filename(split_post_id(post_id)[1]),
        crawled_at=crawled_at,
        push_count=0,
        boo_count=0,
        is_deleted=True,
        comments=[],
    )


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("crawler")
    settings = CrawlerSettings()
    kafka = get_kafka_settings()
    producer = JsonProducer(kafka)
    client = PttClient(
        RateLimiter(settings.min_interval_s, settings.jitter_s),
        base_url_override=settings.ptt_base_url,
    )
    if settings.ptt_base_url:
        log.warning("requests redirected to %s (end-to-end test mode)", settings.ptt_base_url)
    handler = CrawlHandler(
        client, producer, ListPushCache(), RecentFetches(), clock=lambda: datetime.now(UTC)
    )
    consumer = BatchConsumer(
        kafka,
        group_id="crawler",
        topics=[names.CRAWL_TASKS],
        model=CrawlTask,
        handler=handler,
        dlq=DlqPublisher(producer, "crawler"),
        # 一個列表任務可能牽動約 20 次請求，整批重試代價高，一次只處理一個
        batch_size=1,
    )
    try:
        consumer.run()
    finally:
        client.close()
        producer.flush()


if __name__ == "__main__":
    main()

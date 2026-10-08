"""爬蟲：消費 crawl.tasks，抓 PTT 頁面，寫入 raw.posts 與 raw.html。不碰 PG（設計文件 4.6）。"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from pydantic import ValidationError

from radar.collector.http import FetchError, FetchResult, PttClient, PttFetcher
from radar.collector.list_cache import ListPushCache
from radar.collector.parsers.ptt import (
    ListPage,
    ParseError,
    parse_list_page,
    parse_post_page,
    post_id_from_url,
)
from radar.collector.parsers.ptt_time import created_at_from_filename
from radar.common.enums import CrawlTaskType
from radar.common.ids import split_post_id
from radar.common.kafka import names
from radar.common.kafka.consumer import BatchConsumer, TransientError
from radar.common.kafka.dlq import DlqPublisher
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.rate_limit import RateLimiter
from radar.common.schemas import CrawlTask, RawHtml, RawPost
from radar.common.settings import CrawlerSettings, get_kafka_settings


class CrawlHandler:
    """BatchConsumer 的 handler；HTTP 暫時性錯誤以 TransientError 往外拋，讓整批重試。"""

    def __init__(
        self,
        fetcher: PttFetcher,
        producer: JsonProducer,
        cache: ListPushCache,
        *,
        clock: Callable[[], datetime],
        max_list_pages: int = 3,
        max_transient_attempts: int = 5,
    ) -> None:
        self._fetcher = fetcher
        self._producer = producer
        self._cache = cache
        self._clock = clock
        self._max_list_pages = max_list_pages
        self._max_transient_attempts = max_transient_attempts
        # 各網址連續暫時性失敗的次數；成功或略過後移除
        self._transient_attempts: dict[str, int] = {}

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
        """回傳抓了幾篇內頁。

        第一頁的文章若全都沒見過、且快取不是空的，代表兩次輪詢間新文章超過一頁，
        再往前翻，最多 max_list_pages 頁。
        """
        cache_was_empty = len(self._cache) == 0
        url: str | None = task.url
        fetched = 0
        for _ in range(self._max_list_pages):
            if url is None:
                break
            page = self._fetch_list(url, task.board)
            if page is None:
                break
            linked = [e for e in page.entries if e.post_id]
            all_new = bool(linked) and all(e.post_id not in self._cache for e in linked)
            for entry in page.entries:
                if entry.url and self._cache.should_fetch(entry):
                    fetched += self.fetch_and_publish_post(entry.url, task.board, task.task_id)
                self._cache.remember(entry)
            if cache_was_empty or not all_new:
                break
            url = page.prev_page_url
        log.info("list %s done, fetched %d posts", task.board, fetched)
        return fetched

    def handle_post(self, task: CrawlTask) -> None:
        self.fetch_and_publish_post(task.url, task.board, task.task_id)

    def fetch_and_publish_post(self, url: str, board: str, task_id: UUID) -> bool:
        """成功送出 raw.posts 回傳 True；不可重試的失敗記 ERROR 後回傳 False。"""
        post_id = post_id_from_url(url)
        try:
            result = self._fetch(url)
        except FetchError as e:
            log.error("skip post %s: %s", post_id, e)
            return False
        crawled_at = self._clock()
        if result.status == 404:
            self._producer.send(
                names.RAW_POSTS, post_id, deleted_post(post_id, board, url, task_id, crawled_at)
            )
            return True
        html = RawHtml(post_id=post_id, url=url, crawled_at=crawled_at, html=result.html)
        self._producer.send(names.RAW_HTML, post_id, html)
        try:
            post = parse_post_page(
                result.html, board=board, url=url, crawled_at=crawled_at, task_id=task_id
            )
        except (ParseError, ValidationError) as e:
            # raw.html 已送出，修好 parser 後可重新解析
            log.error("parse failed for %s: %s", post_id, e)
            return False
        self._producer.send(names.RAW_POSTS, post_id, post)
        return True

    def _fetch(self, url: str) -> FetchResult:
        """同一網址連續 TransientError 達上限就改拋 FetchError（略過），避免卡住 partition。"""
        try:
            result = self._fetcher.fetch(url)
        except TransientError as e:
            attempts = self._transient_attempts.get(url, 0) + 1
            if attempts >= self._max_transient_attempts:
                self._transient_attempts.pop(url, None)
                raise FetchError(f"{e} (gave up after {attempts} attempts)") from e
            self._transient_attempts[url] = attempts
            raise
        self._transient_attempts.pop(url, None)
        return result

    def _fetch_list(self, url: str, board: str) -> ListPage | None:
        try:
            result = self._fetch(url)
            if result.status != 200:
                raise FetchError(f"list page {url} returned {result.status}")
            return parse_list_page(result.html, board)
        except (FetchError, ParseError) as e:
            # 不重試，避免卡住 partition；下一輪輪詢會再試
            log.error("skip list %s: %s", url, e)
            return None


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
    handler = CrawlHandler(client, producer, ListPushCache(), clock=lambda: datetime.now(UTC))
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

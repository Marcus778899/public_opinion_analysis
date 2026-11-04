"""對指定文章送出重爬任務（reason=recrawl）到 crawl.tasks，不碰 PG。

用法：python tools/recrawl_posts.py <post_id>... 或 --file <每行一個 post_id 的檔案>
"""

import argparse
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from radar.common.enums import CrawlReason
from radar.common.ids import PTT_BASE_URL, split_post_id
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.schemas import CrawlTask
from radar.common.settings import get_kafka_settings
from radar.common.tasks import make_post_task


def parse_post_ids(raw: Iterable[str]) -> list[str]:
    """去掉空白行與重複（保留順序）；格式不對的直接丟 ValueError，不送半批。"""
    seen: dict[str, None] = {}
    for line in raw:
        post_id = line.strip()
        if not post_id:
            continue
        split_post_id(post_id)
        seen[post_id] = None
    return list(seen)


def build_tasks(post_ids: Iterable[str], now: datetime | None = None) -> list[CrawlTask]:
    # NOTE: created_at 取現在，爬蟲才不會把它當成「已抓過」而略過（開發規格 7.12）
    now = now or datetime.now(UTC)
    tasks = []
    for post_id in post_ids:
        board, filename = split_post_id(post_id)
        url = f"{PTT_BASE_URL}/bbs/{board}/{filename}.html"
        tasks.append(make_post_task(post_id, board, url, CrawlReason.RECRAWL, now))
    return tasks


def send_tasks(producer: JsonProducer, tasks: Iterable[CrawlTask]) -> int:
    count = 0
    for task in tasks:
        producer.send(names.CRAWL_TASKS, task.kafka_key(), task)
        count += 1
    producer.flush()
    return count


def read_ids(args: argparse.Namespace) -> list[str]:
    raw: list[str] = list(args.post_ids)
    if args.file:
        raw.extend(Path(args.file).read_text(encoding="utf-8").splitlines())
    return parse_post_ids(raw)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("post_ids", nargs="*")
    parser.add_argument("--file")
    return parser.parse_args(argv)


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("recrawl-posts")
    post_ids = read_ids(parse_args())
    if not post_ids:
        raise SystemExit("no post_id given")
    sent = send_tasks(JsonProducer(get_kafka_settings()), build_tasks(post_ids))
    log.info("sent %d recrawl tasks", sent)


if __name__ == "__main__":
    main()

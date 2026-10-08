"""[一次性] 初期批次標註（S3-02）：抽樣 → LLM 標註 → 送 Kafka labels。

用法：python -m radar.ml.labeling.backfill --per-board 1000
可中斷續跑；每日額度用完會停止，隔天以相同參數再執行即可。
"""

import argparse
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from radar.common.clickhouse import ClickHouseClient
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.retry import backoff_delays
from radar.common.schemas import Label
from radar.common.settings import ClickHouseSettings, LabelingSettings, get_kafka_settings
from radar.ml.labeling.factory import build_labeler
from radar.ml.labeling.llm import (
    Labeler,
    LabelerError,
    QuotaExhaustedError,
    RetryableLabelerError,
)
from radar.ml.labeling.prompt import PROMPT_VERSION, PostText
from radar.ml.labeling.sampling import SampleSpec, sample_posts
from radar.ml.labeling.testset import TESTSET_DIR, load_post_ids

PROGRESS_EVERY = 50


@dataclass(frozen=True)
class BackfillResult:
    labeled: int
    skipped: int
    stopped_by_quota: bool


def run_backfill(
    posts: Sequence[PostText],
    labeler: Labeler,
    version: str,
    publish: Callable[[Label], None],
    *,
    now: Callable[[], datetime],
    max_retries: int = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> BackfillResult:
    labeled = skipped = 0
    for i, post in enumerate(posts, start=1):
        delays = backoff_delays(base_s=2.0, max_s=60.0)
        for attempt in range(max_retries + 1):
            try:
                sentiments = labeler.label(post)
            except RetryableLabelerError as e:
                if attempt == max_retries:
                    log.error("give up %s after %d retries: %s", post.post_id, max_retries, e)
                    skipped += 1
                    break
                sleep(next(delays))
                continue
            except LabelerError as e:
                log.warning("skip %s: %s", post.post_id, e)
                skipped += 1
                break
            except QuotaExhaustedError as e:
                log.warning("stop: %s (labeled=%d, run again tomorrow)", e, labeled)
                return BackfillResult(labeled, skipped, stopped_by_quota=True)
            publish(
                Label(
                    post_id=post.post_id,
                    labeler=labeler.name,
                    version=version,
                    labeled_at=now(),
                    sentiments=sentiments,
                )
            )
            labeled += 1
            break
        if i % PROGRESS_EVERY == 0:
            log.info("progress %d/%d (labeled=%d skipped=%d)", i, len(posts), labeled, skipped)
    return BackfillResult(labeled, skipped, stopped_by_quota=False)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM 批次標註（S3-02）")
    parser.add_argument("--labeler", help="服務商（gemini、groq、openrouter）；預設 LABEL_PRIMARY")
    parser.add_argument("--per-board", type=int, required=True, help="每個看板標註篇數")
    parser.add_argument("--seed", type=int, default=20261007)
    parser.add_argument("--boards", nargs="*", help="只抽這些看板；預設全部")
    parser.add_argument("--dry-run", action="store_true", help="只印抽樣結果，不呼叫 LLM")
    return parser.parse_args(argv)


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("label-backfill")
    args = parse_args()
    settings = LabelingSettings()
    labeler = build_labeler(args.labeler or settings.primary, settings.max_chars)
    testset = set(load_post_ids(TESTSET_DIR))
    spec = SampleSpec(
        per_board=args.per_board,
        seed=args.seed,
        boards=args.boards,
        skip_labeler=labeler.name,
        skip_version=PROMPT_VERSION,
        extra_per_board=len(testset),
    )
    ch = ClickHouseClient(ClickHouseSettings())
    try:
        posts = sample_posts(ch, spec, exclude_ids=testset)
    finally:
        ch.close()
    by_board: dict[str, int] = {}
    for p in posts:
        by_board[p.board] = by_board.get(p.board, 0) + 1
    log.info(
        "sampled %d posts to label with %s/%s: %s",
        len(posts),
        labeler.name,
        PROMPT_VERSION,
        by_board,
    )
    if args.dry_run:
        return

    producer = JsonProducer(get_kafka_settings())

    def publish(label: Label) -> None:
        producer.send(names.LABELS, label.post_id, label)

    try:
        result = run_backfill(
            posts, labeler, PROMPT_VERSION, publish, now=lambda: datetime.now(UTC)
        )
    finally:
        producer.flush()
        labeler.close()
    log.info("done: %s", result)


if __name__ == "__main__":
    main()

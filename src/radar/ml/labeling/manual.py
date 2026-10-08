"""Claude 手動標註（S3-03 第二標註者，開發規格 7.11）。

流程：export 匯出一批文章 → Claude Code 執行 skill /label-posts 標註
→ import 驗證後送 Kafka labels。
用法：
  python -m radar.ml.labeling.manual export --size 50
  python -m radar.ml.labeling.manual import data/manual/batch-20261007T1200.out.jsonl
"""

import argparse
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from radar.common.clickhouse import ClickHouseClient
from radar.common.kafka import names
from radar.common.kafka.producer import JsonProducer
from radar.common.log import log, setup_logging
from radar.common.schemas import Label, Sentiment
from radar.common.settings import ClickHouseSettings, LabelingSettings, get_kafka_settings
from radar.ml.labeling.factory import build_labeler
from radar.ml.labeling.prompt import PROMPT_VERSION
from radar.ml.labeling.sampling import array_param
from radar.ml.labeling.testset import TESTSET_DIR, load_post_ids

MANUAL_LABELER = "claude-sonnet-manual"
MANUAL_DIR = Path("data/manual")


class BatchPost(BaseModel):
    post_id: str
    board: str
    title: str | None
    content: str | None


class ManualOutput(BaseModel):
    post_id: str
    sentiments: list[Sentiment]


def export_query() -> str:
    """主要標註者已標、Claude 尚未標（同一 prompt 版本）的文章；交叉比對需要兩邊都標過。"""
    return (
        "SELECT p.post_id AS post_id, p.board AS board, p.title AS title, p.content AS content\n"
        "FROM posts_latest AS p FINAL\n"
        "WHERE NOT p.is_deleted AND p.post_id IN (\n"
        "  SELECT post_id FROM labels\n"
        "  WHERE labeler = {primary:String} AND version = {version:String}\n"
        ") AND p.post_id NOT IN (\n"
        "  SELECT post_id FROM labels\n"
        "  WHERE labeler = {manual:String} AND version = {version:String}\n"
        ")\n"
        "ORDER BY cityHash64(p.post_id)\n"
        "LIMIT {limit:UInt32}"
    )


def export_batch(
    client: ClickHouseClient,
    primary: str,
    size: int,
    exclude_ids: set[str],
    max_chars: int,
    out_dir: Path,
    now: datetime,
) -> Path | None:
    params = {
        "primary": primary,
        "manual": MANUAL_LABELER,
        "version": PROMPT_VERSION,
        "limit": str(size + len(exclude_ids)),
    }
    rows = [r for r in client.query_rows(export_query(), params) if r["post_id"] not in exclude_ids]
    return _write_batch(rows[:size], max_chars, out_dir, now)


def export_testset_query() -> str:
    """人工測試集中 Claude 尚未標過（同一 prompt 版本）的文章；不要求主要標註者先標。"""
    return (
        "SELECT post_id, board, title, content FROM posts_latest FINAL\n"
        "WHERE post_id IN {ids:Array(String)} AND post_id NOT IN (\n"
        "  SELECT post_id FROM labels\n"
        "  WHERE labeler = {manual:String} AND version = {version:String}\n"
        ")\n"
        "ORDER BY post_id\n"
        "LIMIT {limit:UInt32}"
    )


def export_testset_batch(
    client: ClickHouseClient,
    post_ids: list[str],
    size: int,
    max_chars: int,
    out_dir: Path,
    now: datetime,
) -> Path | None:
    """匯出一批人工測試集給 Claude 標；沒有剩下的回傳 None。檔名與截斷規則同 export_batch。"""
    if not post_ids:
        return None
    params = {
        "ids": array_param(post_ids),
        "manual": MANUAL_LABELER,
        "version": PROMPT_VERSION,
        "limit": str(size),
    }
    return _write_batch(client.query_rows(export_testset_query(), params), max_chars, out_dir, now)


def _write_batch(
    rows: list[dict[str, str]], max_chars: int, out_dir: Path, now: datetime
) -> Path | None:
    if not rows:
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"batch-{now:%Y%m%dT%H%M%S}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            # 截斷規則與 LLM prompt 相同，兩個標註者看到的內容一致
            content = (r.get("content") or "")[:max_chars]
            post = BatchPost(
                post_id=r["post_id"], board=r["board"], title=r.get("title"), content=content
            )
            f.write(post.model_dump_json() + "\n")
    return path


def read_batch(path: Path) -> list[BatchPost]:
    return [
        BatchPost.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


def import_outputs(
    output_path: Path,
    batch: list[BatchPost],
    publish: Callable[[Label], None],
    now: Callable[[], datetime],
) -> tuple[int, list[str]]:
    """回傳 (成功筆數, 錯誤訊息)；任何一筆有錯就整批不送，修正後重新 import。"""
    allowed = {p.post_id for p in batch}
    labels: list[Label] = []
    errors: list[str] = []
    seen: set[str] = set()
    for lineno, line in enumerate(output_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            out = ManualOutput.model_validate_json(line)
            if out.post_id not in allowed:
                raise ValueError(f"{out.post_id} is not in the batch")
            if out.post_id in seen:
                raise ValueError(f"{out.post_id} appears twice")
            seen.add(out.post_id)
            labels.append(
                Label(
                    post_id=out.post_id,
                    labeler=MANUAL_LABELER,
                    version=PROMPT_VERSION,
                    labeled_at=now(),
                    sentiments=out.sentiments,
                )
            )
        except (ValidationError, ValueError, json.JSONDecodeError) as e:
            errors.append(f"line {lineno}: {e}")
    if errors:
        return 0, errors
    for label in labels:
        publish(label)
    return len(labels), []


def batch_path_for(output_path: Path) -> Path:
    """batch-X.out.jsonl → batch-X.jsonl"""
    name = output_path.name
    if not name.endswith(".out.jsonl"):
        raise ValueError(f"{output_path} should be named <batch>.out.jsonl")
    return output_path.with_name(name.removesuffix(".out.jsonl") + ".jsonl")


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("label-manual")
    parser = argparse.ArgumentParser(description="Claude 手動標註的匯出與匯入")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export")
    exp.add_argument("--size", type=int, default=50)
    exp.add_argument("--testset", action="store_true", help="匯出人工測試集（評估用）")
    imp = sub.add_parser("import")
    imp.add_argument("output", type=Path)
    args = parser.parse_args()
    settings = LabelingSettings()

    if args.command == "export" and args.testset:
        ch = ClickHouseClient(ClickHouseSettings())
        try:
            path = export_testset_batch(
                ch,
                load_post_ids(TESTSET_DIR),
                args.size,
                settings.max_chars,
                MANUAL_DIR,
                datetime.now(UTC),
            )
        finally:
            ch.close()
        log.info("exported %s", path or "nothing: every testset post already has a manual label")
        return

    if args.command == "export":
        # 只需要主要標註者的名稱，不會真的呼叫它
        primary = build_labeler(settings.primary, settings.max_chars)
        primary.close()
        ch = ClickHouseClient(ClickHouseSettings())
        try:
            path = export_batch(
                ch,
                primary.name,
                args.size,
                set(load_post_ids(TESTSET_DIR)),
                settings.max_chars,
                MANUAL_DIR,
                datetime.now(UTC),
            )
        finally:
            ch.close()
        log.info(
            "exported %s", path or "nothing: every primary-labeled post already has a manual label"
        )
        return

    batch = read_batch(batch_path_for(args.output))
    producer = JsonProducer(get_kafka_settings())
    count, errors = import_outputs(
        args.output,
        batch,
        lambda label: producer.send(names.LABELS, label.post_id, label),
        lambda: datetime.now(UTC),
    )
    producer.flush()
    if errors:
        for e in errors:
            log.error("%s", e)
        raise SystemExit(1)
    missing = len(batch) - count
    log.info(
        "imported %d labels%s",
        count,
        f" ({missing} posts in the batch not labeled)" if missing else "",
    )


if __name__ == "__main__":
    main()

"""[一次性] 匯出訓練資料（S3-06，設計文件 7.6）：posts_latest join labels。

用法：python -m radar.ml.training.export
輸出 data/datasets/<名稱>.jsonl 與同名 .meta.json（訓練時寫進 model_card）。
"""

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings, LabelingSettings
from radar.ml.labeling.cross_check import fetch_whole_post_labels
from radar.ml.labeling.factory import build_labeler
from radar.ml.labeling.manual import MANUAL_LABELER
from radar.ml.labeling.prompt import PROMPT_VERSION
from radar.ml.labeling.testset import TESTSET_DIR, load_post_ids
from radar.ml.training.dataset import Example, class_counts, post_text, write_jsonl

DATASETS_DIR = Path("data/datasets")

ROWS_QUERY = (
    "SELECT l.post_id AS post_id, p.board AS board, p.title AS title, p.content AS content,\n"
    "       l.polarity AS polarity\n"
    "FROM (\n"
    "  SELECT post_id, argMax(polarity, labeled_at) AS polarity FROM labels\n"
    "  WHERE labeler = {labeler:String} AND version = {version:String} AND target IS NULL\n"
    "  GROUP BY post_id\n"
    ") AS l\n"
    "INNER JOIN (\n"
    "  SELECT post_id, board, title, content FROM posts_latest FINAL WHERE NOT is_deleted\n"
    ") AS p USING post_id\n"
    "ORDER BY post_id"
)


@dataclass(frozen=True)
class ExportStats:
    excluded_testset: int
    dropped_disagreements: int


def build_examples(
    rows: list[dict[str, str]],
    secondary: dict[str, Polarity],
    exclude_ids: set[str],
    max_chars: int,
) -> tuple[list[Example], ExportStats]:
    """rows 為主要標註者的整篇標註 join 文章內容。

    排除人工測試集；次要標註者也標過且整篇情緒不同的文章不收（開發規格 7.11）。
    """
    examples: list[Example] = []
    excluded = dropped = 0
    for r in rows:
        polarity = Polarity(r["polarity"])
        if r["post_id"] in exclude_ids:
            excluded += 1
            continue
        if r["post_id"] in secondary and secondary[r["post_id"]] != polarity:
            dropped += 1
            continue
        text = post_text(r.get("title"), r.get("content"), max_chars)
        examples.append(Example(r["post_id"], r["board"], text, polarity))
    return examples, ExportStats(excluded_testset=excluded, dropped_disagreements=dropped)


def fetch_rows(client: ClickHouseClient, labeler: str, version: str) -> list[dict[str, str]]:
    return client.query_rows(ROWS_QUERY, {"labeler": labeler, "version": version})


def dataset_name(labeler: str, version: str, now: datetime) -> str:
    safe = "".join(c if c.isalnum() or c in "-." else "-" for c in labeler)
    return f"{safe}-{version}-{now:%Y%m%d%H%M}"


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("train-export")
    parser = argparse.ArgumentParser(description="匯出訓練資料（S3-06）")
    parser.add_argument("--labeler", help="主要標註者的 labeler 名稱；預設由 LABEL_PRIMARY 推得")
    parser.add_argument("--secondary", default=MANUAL_LABELER)
    parser.add_argument("--version", default=PROMPT_VERSION)
    args = parser.parse_args()
    settings = LabelingSettings()
    labeler = args.labeler
    if labeler is None:
        built = build_labeler(settings.primary, settings.max_chars)
        labeler = built.name
        built.close()

    ch = ClickHouseClient(ClickHouseSettings())
    try:
        rows = fetch_rows(ch, labeler, args.version)
        secondary = fetch_whole_post_labels(ch, args.secondary, args.version)
    finally:
        ch.close()
    testset = set(load_post_ids(TESTSET_DIR))
    examples, stats = build_examples(rows, secondary, testset, settings.max_chars)

    now = datetime.now(UTC)
    path = DATASETS_DIR / f"{dataset_name(labeler, args.version, now)}.jsonl"
    write_jsonl(path, examples)
    meta = {
        "dataset": path.name,
        "created_at": now.isoformat(),
        "labeler": labeler,
        "label_version": args.version,
        "secondary": args.secondary,
        "max_chars": settings.max_chars,
        "n": len(examples),
        "class_counts": class_counts(examples),
        "excluded_testset": stats.excluded_testset,
        "dropped_disagreements": stats.dropped_disagreements,
    }
    path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    log.info("exported %d examples to %s: %s", len(examples), path, meta["class_counts"])


if __name__ == "__main__":
    main()

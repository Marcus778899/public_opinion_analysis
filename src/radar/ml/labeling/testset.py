"""人工測試集（S3-04）：抽樣、讀寫人工標註。這些文章永遠不進訓練資料。"""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel, model_validator

from radar.common.clickhouse import ClickHouseClient
from radar.common.log import log, setup_logging
from radar.common.schemas import Sentiment, UtcDatetime, check_sentiments
from radar.common.settings import ClickHouseSettings
from radar.ml.labeling.sampling import SampleSpec, sample_posts

TESTSET_DIR = Path("data/testset")
POST_IDS_FILE = "post_ids.txt"
HUMAN_LABELS_FILE = "human_labels.jsonl"
# 與 backfill 預設 seed 不同，抽到的文章才不會集中在 backfill 的前段
TESTSET_SEED = 300


class HumanLabel(BaseModel):
    post_id: str
    sentiments: list[Sentiment]
    labeled_at: UtcDatetime
    note: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "HumanLabel":
        check_sentiments(self.sentiments)
        return self


def select_testset(client: ClickHouseClient, size: int, boards: list[str]) -> list[str]:
    """各看板平均分配；除不盡的餘數給排在前面的看板。"""
    base, extra = divmod(size, len(boards))
    ids: list[str] = []
    for i, board in enumerate(boards):
        spec = SampleSpec(
            per_board=base + (1 if i < extra else 0), seed=TESTSET_SEED, boards=[board]
        )
        ids.extend(p.post_id for p in sample_posts(client, spec, exclude_ids=set()))
    return ids


def write_post_ids(directory: Path, post_ids: list[str]) -> None:
    path = directory / POST_IDS_FILE
    if path.exists():
        # 換掉測試集會讓已標的人工標註對不上，要重抽就手動刪檔
        raise FileExistsError(f"{path} already exists; delete it manually to resample")
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{pid}\n" for pid in post_ids))


def load_post_ids(directory: Path) -> list[str]:
    path = directory / POST_IDS_FILE
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def load_human_labels(directory: Path) -> dict[str, HumanLabel]:
    """同一篇標過多次以最後一筆為準（允許改標）。"""
    path = directory / HUMAN_LABELS_FILE
    if not path.exists():
        return {}
    labels: dict[str, HumanLabel] = {}
    for line in path.read_text().splitlines():
        if line.strip():
            label = HumanLabel.model_validate_json(line)
            labels[label.post_id] = label
    return labels


def append_human_label(directory: Path, label: HumanLabel) -> None:
    # NOTE: 只附加不改寫，標註過程中斷也不會毀掉已標的資料
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / HUMAN_LABELS_FILE).open("a", encoding="utf-8") as f:
        f.write(json.dumps(label.model_dump(mode="json"), ensure_ascii=False) + "\n")


@log.catch(level="CRITICAL")
def main() -> None:
    """用法：python -m radar.ml.labeling.testset --size 300 --boards Gossiping Stock Tech_Job"""
    setup_logging("testset")
    parser = argparse.ArgumentParser(description="抽出人工測試集（S3-04）")
    parser.add_argument("--size", type=int, default=300)
    parser.add_argument("--boards", nargs="+", required=True)
    args = parser.parse_args()
    ch = ClickHouseClient(ClickHouseSettings())
    try:
        ids = select_testset(ch, args.size, args.boards)
    finally:
        ch.close()
    write_post_ids(TESTSET_DIR, ids)
    log.info("testset: %d posts written to %s", len(ids), TESTSET_DIR / POST_IDS_FILE)


if __name__ == "__main__":
    main()

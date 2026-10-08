"""[一次性] 兩個標註者交叉比對（S3-03）：輸出一致率與不一致清單 CSV 供人工檢查。

用法：python -m radar.ml.labeling.cross_check --out data/review/disagreements.csv
預設比對主要標註者（LABEL_PRIMARY）與 Claude 手動標註。
"""

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

from sklearn.metrics import cohen_kappa_score

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.ids import PTT_BASE_URL, split_post_id
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings, LabelingSettings
from radar.ml.labeling.factory import build_labeler
from radar.ml.labeling.manual import MANUAL_LABELER
from radar.ml.labeling.prompt import PROMPT_VERSION, PostText
from radar.ml.labeling.sampling import fetch_posts

CSV_FIELDS = ["post_id", "board", "title", "primary", "secondary", "human", "url"]


@dataclass(frozen=True)
class Disagreement:
    post_id: str
    primary: Polarity
    secondary: Polarity


@dataclass(frozen=True)
class AgreementSummary:
    overlap: int
    agreed: int
    cohen_kappa: float

    @property
    def rate(self) -> float:
        return self.agreed / self.overlap if self.overlap else 0.0


WHOLE_POST_QUERY = (
    "SELECT post_id, argMax(polarity, labeled_at) AS polarity FROM labels\n"
    "WHERE labeler = {labeler:String} AND version = {version:String} AND target IS NULL\n"
    "GROUP BY post_id"
)


def fetch_whole_post_labels(
    client: ClickHouseClient, labeler: str, version: str
) -> dict[str, Polarity]:
    """同一篇有多筆時取 labeled_at 最新的（重標過的以新的為準）。"""
    rows = client.query_rows(WHOLE_POST_QUERY, {"labeler": labeler, "version": version})
    return {r["post_id"]: Polarity(r["polarity"]) for r in rows}


def kappa(a: list[Polarity], b: list[Polarity]) -> float:
    """Cohen's kappa；兩邊都只有同一個類別時 kappa 沒有定義，視為完全一致。"""
    if not a:
        return 0.0
    if len(set(a) | set(b)) == 1:
        return 1.0
    return float(cohen_kappa_score(a, b, labels=list(Polarity)))


def compare(
    primary: dict[str, Polarity], secondary: dict[str, Polarity]
) -> tuple[AgreementSummary, list[Disagreement]]:
    overlap = sorted(primary.keys() & secondary.keys())
    a = [primary[p] for p in overlap]
    b = [secondary[p] for p in overlap]
    disagreements = [
        Disagreement(p, primary[p], secondary[p]) for p in overlap if primary[p] != secondary[p]
    ]
    summary = AgreementSummary(
        overlap=len(overlap), agreed=len(overlap) - len(disagreements), cohen_kappa=kappa(a, b)
    )
    return summary, disagreements


def post_url(post_id: str) -> str:
    board, filename = split_post_id(post_id)
    return f"{PTT_BASE_URL}/bbs/{board}/{filename}.html"


def write_disagreements_csv(
    rows: list[Disagreement], posts: dict[str, PostText], path: Path
) -> None:
    """human 欄留空給人工填；用 Excel 開也不會亂碼（utf-8-sig）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for d in rows:
            post = posts.get(d.post_id)
            writer.writerow(
                {
                    "post_id": d.post_id,
                    "board": post.board if post else split_post_id(d.post_id)[0],
                    "title": post.title if post else "",
                    "primary": d.primary.value,
                    "secondary": d.secondary.value,
                    "human": "",
                    "url": post_url(d.post_id),
                }
            )


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("label-cross-check")
    parser = argparse.ArgumentParser(description="兩個標註者的交叉比對（S3-03）")
    parser.add_argument("--primary", help="主要標註者的 labeler 名稱；預設由 LABEL_PRIMARY 推得")
    parser.add_argument("--secondary", default=MANUAL_LABELER)
    parser.add_argument("--version", default=PROMPT_VERSION)
    parser.add_argument("--out", type=Path, default=Path("data/review/disagreements.csv"))
    args = parser.parse_args()
    primary_name = args.primary
    if primary_name is None:
        settings = LabelingSettings()
        labeler = build_labeler(settings.primary, settings.max_chars)
        primary_name = labeler.name
        labeler.close()

    ch = ClickHouseClient(ClickHouseSettings())
    try:
        primary = fetch_whole_post_labels(ch, primary_name, args.version)
        secondary = fetch_whole_post_labels(ch, args.secondary, args.version)
        summary, disagreements = compare(primary, secondary)
        posts = fetch_posts(ch, [d.post_id for d in disagreements])
    finally:
        ch.close()
    write_disagreements_csv(disagreements, posts, args.out)
    log.info(
        "%s vs %s (%s): overlap=%d agreement=%.1f%% kappa=%.3f; %d disagreements -> %s",
        primary_name,
        args.secondary,
        args.version,
        summary.overlap,
        summary.rate * 100,
        summary.cohen_kappa,
        len(disagreements),
        args.out,
    )


if __name__ == "__main__":
    main()

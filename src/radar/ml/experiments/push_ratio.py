"""[一次性] 推噓比弱標註實驗（S3-05，設計文件 15.6）。

比較 LLM 各情緒類別的推噓比分布；相關性弱就不當標籤，改當特徵或獨立指標。
用法：python -m radar.ml.experiments.push_ratio --out docs/reports/s3-05-push-ratio.md
"""

import argparse
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings, LabelingSettings
from radar.ml.labeling.factory import build_labeler
from radar.ml.labeling.prompt import PROMPT_VERSION

# 推噓總數太少時比例沒有意義
MIN_VOTES = 10
ORDINAL = {Polarity.NEGATIVE: -1, Polarity.NEUTRAL: 0, Polarity.POSITIVE: 1}


@dataclass(frozen=True)
class PostVotes:
    post_id: str
    polarity: Polarity
    push_count: int
    boo_count: int


@dataclass(frozen=True)
class RatioSummary:
    polarity: Polarity
    n: int
    median: float
    p25: float
    p75: float


VOTES_QUERY = (
    "SELECT l.post_id AS post_id, l.polarity AS polarity, p.push_count AS push_count,\n"
    "       p.boo_count AS boo_count\n"
    "FROM (\n"
    "  SELECT post_id, argMax(polarity, labeled_at) AS polarity FROM labels\n"
    "  WHERE labeler = {labeler:String} AND version = {version:String} AND target IS NULL\n"
    "  GROUP BY post_id\n"
    ") AS l\n"
    "INNER JOIN (SELECT post_id, push_count, boo_count FROM posts_latest FINAL) AS p\n"
    "USING post_id"
)


def push_ratio(push: int, boo: int) -> float | None:
    total = push + boo
    return push / total if total >= MIN_VOTES else None


def fetch_votes(client: ClickHouseClient, labeler: str, version: str) -> list[PostVotes]:
    rows = client.query_rows(VOTES_QUERY, {"labeler": labeler, "version": version})
    return [
        PostVotes(r["post_id"], Polarity(r["polarity"]), int(r["push_count"]), int(r["boo_count"]))
        for r in rows
    ]


def _ratios(rows: list[PostVotes]) -> list[tuple[Polarity, float]]:
    pairs = [(r.polarity, push_ratio(r.push_count, r.boo_count)) for r in rows]
    return [(p, ratio) for p, ratio in pairs if ratio is not None]


def summarize(rows: list[PostVotes]) -> list[RatioSummary]:
    """依 polarity 分組算四分位數；略過票數不足的文章，沒有資料的類別不列。"""
    grouped: dict[Polarity, list[float]] = {}
    for polarity, ratio in _ratios(rows):
        grouped.setdefault(polarity, []).append(ratio)
    summaries = []
    for polarity in Polarity:
        values = sorted(grouped.get(polarity, []))
        if not values:
            continue
        if len(values) == 1:
            p25 = p75 = values[0]
        else:
            p25, _, p75 = statistics.quantiles(values, n=4, method="inclusive")
        summaries.append(RatioSummary(polarity, len(values), statistics.median(values), p25, p75))
    return summaries


def spearman(rows: list[PostVotes]) -> float | None:
    """情緒（負 -1／中 0／正 1）與推噓比的等級相關；資料不足或沒有變異時回傳 None。"""
    pairs = _ratios(rows)
    if len(pairs) < 3:
        return None
    x = [ORDINAL[p] for p, _ in pairs]
    y = [ratio for _, ratio in pairs]
    if len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return statistics.correlation(x, y, method="ranked")


def render_report(
    summaries: list[RatioSummary], rho: float | None, labeler: str, version: str, now: datetime
) -> str:
    lines = [
        "# S3-05 推噓比弱標註實驗",
        "",
        f"> 產生時間：{now:%Y-%m-%d %H:%M} UTC；標註者：`{labeler}`（{version}）；"
        f"只計推噓總數 ≥ {MIN_VOTES} 的文章",
        "",
        "推噓比 = 推 / (推 + 噓)。若推噓比能當弱標註，各情緒類別的分布應明顯分開。",
        "",
        "| 整篇情緒 | 篇數 | 推噓比中位數 | P25 | P75 |",
        "|---|---|---|---|---|",
        *(
            f"| {s.polarity.value} | {s.n} | {s.median:.2f} | {s.p25:.2f} | {s.p75:.2f} |"
            for s in summaries
        ),
        "",
        f"Spearman 等級相關（情緒 vs 推噓比）：{'資料不足' if rho is None else f'{rho:.3f}'}",
        "",
        "## 結論",
        "",
        "（由人判斷後填寫：採用 / 改當特徵 / 不採用，以及理由）",
        "",
    ]
    return "\n".join(lines)


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("exp-push-ratio")
    parser = argparse.ArgumentParser(description="推噓比弱標註實驗（S3-05）")
    parser.add_argument("--labeler", help="labeler 名稱；預設由 LABEL_PRIMARY 推得")
    parser.add_argument("--version", default=PROMPT_VERSION)
    parser.add_argument("--out", type=Path, default=Path("docs/reports/s3-05-push-ratio.md"))
    args = parser.parse_args()
    labeler = args.labeler
    if labeler is None:
        settings = LabelingSettings()
        built = build_labeler(settings.primary, settings.max_chars)
        labeler = built.name
        built.close()
    ch = ClickHouseClient(ClickHouseSettings())
    try:
        rows = fetch_votes(ch, labeler, args.version)
    finally:
        ch.close()
    report = render_report(
        summarize(rows), spearman(rows), labeler, args.version, datetime.now(UTC)
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report)
    log.info("report written to %s (%d labeled posts)", args.out, len(rows))


if __name__ == "__main__":
    main()

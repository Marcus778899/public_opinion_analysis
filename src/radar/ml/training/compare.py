"""[一次性] 比較現行與 shadow 兩個模型版本（開發規格 7.27「比較」，S8-03）。

用法：python -m radar.ml.training.compare --a <現行版本> --b <shadow 版本> --since <UTC 時間>
產物：models/<b>/comparison.md、data/review/disagreements-<a>-vs-<b>.csv；查詢全部參數化。
"""

import argparse
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sklearn.metrics import f1_score

from radar.common.cli import load_settings
from radar.common.clickhouse import ClickHouseClient
from radar.common.csv_safe import csv_safe
from radar.common.enums import Polarity
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings, InferenceRole, LabelingSettings
from radar.ml.inference.roles import ROLE_TARGETS
from radar.ml.labeling.factory import build_labeler
from radar.ml.labeling.prompt import PROMPT_VERSION
from radar.ml.training.import_model import MODEL_VERSION_RE

REVIEW_DIR = Path("data/review")
REPORT_FILE = "comparison.md"
# 信心分布的門檻（設計文件 15.8；重新決定 TELEGRAM_SENTIMENT_MIN_SCORE 用）
CONFIDENCE_THRESHOLDS = (0.4, 0.5, 0.6, 0.7)
MODELS_DIR = Path("models")


def model_version_arg(value: str) -> str:
    if not MODEL_VERSION_RE.fullmatch(value):
        raise argparse.ArgumentTypeError(f"版本格式不符 {MODEL_VERSION_RE.pattern}：{value!r}")
    return value


def _latest_prediction(table: str, version_param: str) -> str:
    """每版每篇取最新一筆；polarity 與信心（最高分）用 tuple 取同一列。

    table 只來自 ROLE_TARGETS 常數。
    """
    return (
        "SELECT post_id, pick.1 AS polarity, pick.2 AS score FROM (\n"
        "  SELECT post_id,\n"
        "         argMax((polarity, arrayMax(mapValues(scores))), predicted_at) AS pick\n"
        f"  FROM {table}\n"
        f"  WHERE model_version = {{{version_param}:String}}\n"
        "  GROUP BY post_id\n"
        ")"
    )


def _pairs_query() -> str:
    primary = ROLE_TARGETS[InferenceRole.PRIMARY].table
    shadow = ROLE_TARGETS[InferenceRole.SHADOW].table
    return (
        "SELECT p.post_id AS post_id, p.board AS board, p.title AS title,\n"
        "       a.polarity AS polarity_a, a.score AS score_a,\n"
        "       b.polarity AS polarity_b, b.score AS score_b, l.polarity AS llm\n"
        "FROM (\n"
        "  SELECT post_id, board, ifNull(title, '') AS title FROM posts_latest FINAL\n"
        "  WHERE NOT is_deleted AND created_at >= toDateTime64({since:String}, 6, 'UTC')\n"
        ") AS p\n"
        f"INNER JOIN ({_latest_prediction(primary, 'version_a')}) AS a ON a.post_id = p.post_id\n"
        f"INNER JOIN ({_latest_prediction(shadow, 'version_b')}) AS b ON b.post_id = p.post_id\n"
        "LEFT JOIN (\n"
        "  SELECT post_id, argMax(polarity, labeled_at) AS polarity FROM labels\n"
        "  WHERE labeler = {labeler:String} AND version = {label_version:String}\n"
        "    AND target IS NULL\n"
        "  GROUP BY post_id\n"
        ") AS l ON l.post_id = p.post_id\n"
        "ORDER BY p.post_id"
    )


_LATENCY_QUERY = (
    "SELECT (toUnixTimestamp64Micro(pr.first_at) - toUnixTimestamp64Micro(h.created)) / 1e6\n"
    "       AS latency_s\n"
    "FROM (\n"
    "  SELECT post_id, min(predicted_at) AS first_at FROM {table}\n"
    "  WHERE model_version = {version:String} GROUP BY post_id\n"
    ") AS pr\n"
    "INNER JOIN (\n"
    "  SELECT post_id, min(changed_at) AS created FROM posts_history\n"
    "  WHERE op = 'c' AND changed_at >= toDateTime64({since:String}, 3, 'UTC')\n"
    "  GROUP BY post_id\n"
    ") AS h ON h.post_id = pr.post_id\n"
    "ORDER BY latency_s"
)


def _utc_param(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return f"{moment.astimezone(UTC):%Y-%m-%d %H:%M:%S.%f}"


@dataclass(frozen=True)
class PairedPrediction:
    """兩版各取每篇最新一筆後 INNER JOIN 的一列。"""

    post_id: str
    board: str
    title: str
    polarity_a: Polarity
    score_a: float
    polarity_b: Polarity
    score_b: float
    # LLM 標註（LABEL_PRIMARY、目前 PROMPT_VERSION、整篇）；沒有標註時為 None
    llm: Polarity | None


@dataclass(frozen=True)
class AgreementStats:
    n: int
    accuracy: float
    cohen_kappa: float
    # confusion[a 的類別][b 的類別]
    confusion: dict[Polarity, dict[Polarity, int]]


@dataclass(frozen=True)
class LatencyStats:
    """每篇第一次 predicted_at − posts_history 該篇 op='c' 的 changed_at（秒）。"""

    n: int
    p50_s: float
    p95_s: float
    max_s: float


@dataclass(frozen=True)
class ConfidenceBucket:
    threshold: float
    # 最高分低於門檻的比例
    below_ratio: float
    # 門檻以上對 LLM 標註的準確率與篇數
    accuracy_vs_llm: float
    n_vs_llm: int


def fetch_pairs(
    client: ClickHouseClient, a: str, b: str, since: datetime, labeler: str, label_version: str
) -> list[PairedPrediction]:
    rows = client.query_rows(
        _pairs_query(),
        {
            "since": _utc_param(since),
            "version_a": a,
            "version_b": b,
            "labeler": labeler,
            "label_version": label_version,
        },
    )
    return [
        PairedPrediction(
            post_id=r["post_id"],
            board=r["board"],
            title=r["title"],
            polarity_a=Polarity(r["polarity_a"]),
            score_a=float(r["score_a"]),
            polarity_b=Polarity(r["polarity_b"]),
            score_b=float(r["score_b"]),
            llm=Polarity(r["llm"]) if r["llm"] else None,
        )
        for r in rows
    ]


def percentile(sorted_values: list[float], q: float) -> float:
    """線性內插；空清單回 0。"""
    if not sorted_values:
        return 0.0
    pos = q * (len(sorted_values) - 1)
    low = int(pos)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (pos - low)


def fetch_latency(
    client: ClickHouseClient, model_version: str, role: InferenceRole, since: datetime
) -> LatencyStats:
    sql = _LATENCY_QUERY.replace("{table}", ROLE_TARGETS[role].table)
    rows = client.query_rows(sql, {"version": model_version, "since": _utc_param(since)})
    values = sorted(float(r["latency_s"]) for r in rows)
    return LatencyStats(
        n=len(values),
        p50_s=percentile(values, 0.5),
        p95_s=percentile(values, 0.95),
        max_s=values[-1] if values else 0.0,
    )


def agreement(pairs: list[PairedPrediction]) -> AgreementStats:
    confusion = {pa: {pb: 0 for pb in Polarity} for pa in Polarity}
    for p in pairs:
        confusion[p.polarity_a][p.polarity_b] += 1
    n = len(pairs)
    agreed = sum(confusion[pol][pol] for pol in Polarity)
    return AgreementStats(
        n=n,
        accuracy=agreed / n if n else 0.0,
        cohen_kappa=_kappa(confusion, n, agreed),
        confusion=confusion,
    )


def _kappa(confusion: dict[Polarity, dict[Polarity, int]], n: int, agreed: int) -> float:
    """整數運算到最後一步才相除；兩版全為同一類別時沒有定義，視為完全一致。"""
    if n == 0:
        return 0.0
    chance = sum(
        sum(confusion[pa].values()) * sum(confusion[x][pa] for x in Polarity) for pa in Polarity
    )
    if n * n == chance:
        return 1.0
    return (n * agreed - chance) / (n * n - chance)


def confidence_buckets(scores: list[tuple[float, bool | None]]) -> list[ConfidenceBucket]:
    """scores 為 (最高分, 是否與 LLM 標註一致；沒有標註時 None)。"""
    buckets = []
    for threshold in CONFIDENCE_THRESHOLDS:
        below = sum(1 for score, _ in scores if score < threshold)
        judged = [ok for score, ok in scores if score >= threshold and ok is not None]
        buckets.append(
            ConfidenceBucket(
                threshold=threshold,
                below_ratio=below / len(scores) if scores else 0.0,
                accuracy_vs_llm=sum(judged) / len(judged) if judged else 0.0,
                n_vs_llm=len(judged),
            )
        )
    return buckets


def _confusion_table(stats: AgreementStats) -> list[str]:
    header = "| a＼b | " + " | ".join(p.value for p in Polarity) + " |"
    lines = [header, "|---|" + "---|" * len(Polarity)]
    for pa in Polarity:
        cells = " | ".join(str(stats.confusion[pa][pb]) for pb in Polarity)
        lines.append(f"| {pa.value} | {cells} |")
    return lines


def render_markdown(
    a: str,
    b: str,
    overall: AgreementStats,
    by_board: dict[str, AgreementStats],
    latency: dict[str, LatencyStats],
    confidence: dict[str, list[ConfidenceBucket]],
) -> str:
    lines = [f"# 模型比較：{a} vs {b}", "", "## 兩版一致性", ""]
    lines += ["| 範圍 | 篇數 | 一致率 | Cohen's kappa |", "|---|---|---|---|"]
    scopes = {"整體": overall, **dict(sorted(by_board.items()))}
    for scope, st in scopes.items():
        lines.append(f"| {scope} | {st.n} | {st.accuracy:.1%} | {st.cohen_kappa:.3f} |")
    for scope, st in scopes.items():
        lines += ["", f"### 混淆矩陣：{scope}（列為 {a}、欄為 {b}）", ""]
        lines += _confusion_table(st)
    lines += ["", "## 推論延遲（秒）", ""]
    lines += ["| 版本 | 篇數 | p50 | p95 | 最大 |", "|---|---|---|---|---|"]
    for version, lat in latency.items():
        cells = f"{lat.n} | {lat.p50_s:.3f} | {lat.p95_s:.3f} | {lat.max_s:.3f}"
        lines.append(f"| {version} | {cells} |")
    lines += ["", "## 信心分布", ""]
    for version, buckets in confidence.items():
        lines += [f"### {version}", ""]
        lines += ["| 門檻 | 低於門檻比例 | 門檻以上對 LLM 準確率 | 篇數 |", "|---|---|---|---|"]
        for bk in buckets:
            acc = f"{bk.accuracy_vs_llm:.3f} | {bk.n_vs_llm}"
            lines.append(f"| {bk.threshold} | {bk.below_ratio:.1%} | {acc} |")
        lines.append("")
    return "\n".join(lines) + "\n"


def macro_f1_vs_llm(pairs: list[PairedPrediction], use_b: bool) -> tuple[float, int]:
    """對 LLM 標註的 macro-F1 與篇數；沒有標註時為 (0.0, 0)。"""
    labelled = [p for p in pairs if p.llm is not None]
    if not labelled:
        return 0.0, 0
    truth = [p.llm for p in labelled]
    pred = [p.polarity_b if use_b else p.polarity_a for p in labelled]
    score = f1_score(truth, pred, labels=list(Polarity), average="macro", zero_division=0)
    return float(score), len(labelled)


def render_llm_section(a: str, b: str, pairs: list[PairedPrediction]) -> str:
    # NOTE: 不改 render_markdown 的簽名（跨單介面），LLM 對照另成一節附在後面
    lines = ["## 對 LLM 標註的 macro-F1（代理指標）", ""]
    lines += ["| 版本 | macro-F1 | 篇數 |", "|---|---|---|"]
    for version, use_b in ((a, False), (b, True)):
        f1, n = macro_f1_vs_llm(pairs, use_b)
        lines.append(f"| {version} | {f1:.3f} | {n} |")
    return "\n".join(lines) + "\n"


def write_disagreements(path: Path, pairs: list[PairedPrediction]) -> int:
    """兩版 polarity 不同的列寫成 CSV，回傳列數。"""
    rows = sorted((p for p in pairs if p.polarity_a != p.polarity_b), key=lambda p: p.post_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["post_id", "board", "title", "polarity_a", "score_a", "polarity_b", "score_b", "llm"]
        )
        for p in rows:
            writer.writerow(
                [
                    p.post_id,
                    csv_safe(p.board),
                    csv_safe(p.title),
                    p.polarity_a.value,
                    f"{p.score_a:.3f}",
                    p.polarity_b.value,
                    f"{p.score_b:.3f}",
                    p.llm.value if p.llm else "",
                ]
            )
    return len(rows)


def _conf_scores(pairs: list[PairedPrediction], use_b: bool) -> list[tuple[float, bool | None]]:
    out: list[tuple[float, bool | None]] = []
    for p in pairs:
        pol, score = (p.polarity_b, p.score_b) if use_b else (p.polarity_a, p.score_a)
        out.append((score, None if p.llm is None else pol == p.llm))
    return out


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("compare")
    parser = argparse.ArgumentParser(description="比較現行與 shadow 模型（S8-03）")
    parser.add_argument(
        "--a", type=model_version_arg, required=True, help="現行版本（predictions 的版本）"
    )
    parser.add_argument(
        "--b",
        type=model_version_arg,
        required=True,
        help="shadow 版本（predictions_shadow 的 model_version）",
    )
    parser.add_argument(
        "--since",
        type=datetime.fromisoformat,
        required=True,
        help="只比較此時間之後建立的文章，ISO 格式，例如 2026-10-27T00:00:00+00:00；"
        "沒寫時區視為 UTC",
    )
    args = parser.parse_args()
    ch_settings = load_settings(ClickHouseSettings)

    labeling = LabelingSettings()
    built = build_labeler(labeling.primary, labeling.max_chars)
    labeler = built.name
    built.close()

    ch = ClickHouseClient(ch_settings)
    try:
        pairs = fetch_pairs(ch, args.a, args.b, args.since, labeler, PROMPT_VERSION)
        latency = {
            args.a: fetch_latency(ch, args.a, InferenceRole.PRIMARY, args.since),
            args.b: fetch_latency(ch, args.b, InferenceRole.SHADOW, args.since),
        }
    finally:
        ch.close()

    boards = sorted({p.board for p in pairs})
    by_board = {bd: agreement([p for p in pairs if p.board == bd]) for bd in boards}
    confidence = {
        args.a: confidence_buckets(_conf_scores(pairs, use_b=False)),
        args.b: confidence_buckets(_conf_scores(pairs, use_b=True)),
    }
    report = render_markdown(args.a, args.b, agreement(pairs), by_board, latency, confidence)
    report += "\n" + render_llm_section(args.a, args.b, pairs)
    report_path = MODELS_DIR / args.b / REPORT_FILE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    csv_path = REVIEW_DIR / f"disagreements-{args.a}-vs-{args.b}.csv"
    count = write_disagreements(csv_path, pairs)
    log.info("compared %d posts, %d disagreements; wrote %s", len(pairs), count, report_path)


if __name__ == "__main__":
    main()

"""[一次性] 在人工測試集上評估（S3-06、階段 3 驗收）。

回報 baseline 的 macro-F1 與兩個 LLM 標註者與人工的一致率，整體與各看板分開（開發規格 7.11）。
用法：python -m radar.ml.training.evaluate --model models/<model_version>
"""

import argparse
import math
import resource
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from sklearn.metrics import confusion_matrix, f1_score

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings, InferenceSettings
from radar.ml.labeling.cross_check import fetch_whole_post_labels, kappa
from radar.ml.labeling.manual import MANUAL_LABELER
from radar.ml.labeling.sampling import fetch_posts
from radar.ml.labeling.testset import TESTSET_DIR, load_human_labels
from radar.ml.training.classifier import Classifier, load_classifier, top_class
from radar.ml.training.dataset import Example, post_text
from radar.ml.training.train import write_card

REPORT_FILE = "evaluation.md"
# 看板樣本數低於此值時在輸出註明 F1 只供參考
SMALL_BOARD_N = 50
# 與 InferenceSettings.batch_size 的預設相同
DEFAULT_BATCH_SIZE = 100
BYTES_PER_MB = 1024 * 1024
# NOTE: 測試替換這兩個來源，耗時與 RSS 才不依賴機器
_clock: Callable[[], float] = time.perf_counter


@dataclass(frozen=True)
class ClassificationReport:
    n: int
    macro_f1: float
    per_class_f1: dict[Polarity, float]
    # confusion[真實][預測]
    confusion: dict[Polarity, dict[Polarity, int]]


@dataclass(frozen=True)
class Agreement:
    labeler: str
    n: int
    accuracy: float
    cohen_kappa: float


@dataclass(frozen=True)
class RuntimeStats:
    """CPU 推論耗時與記憶體（開發規格 7.27 步驟 4）；寫進 evaluation.md 供選 fp32／int8。"""

    threads: int
    batch_size: int
    per_post_p50_ms: float
    per_post_p95_ms: float
    # 每批 batch_size 篇的耗時；進 shadow 門檻見 7.27「自行決定」
    per_batch_p50_s: float
    per_batch_max_s: float
    peak_rss_mb: float
    # 載入模型後、推論前的 RSS；None 表示沒量
    load_rss_mb: float | None = None


def _peak_rss_mb() -> float:
    # NOTE: ru_maxrss 在 macOS 是 bytes、Linux 是 KB
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / BYTES_PER_MB if sys.platform == "darwin" else peak / 1024


def _percentile(sorted_values: list[float], q: float) -> float:
    """nearest-rank 百分位；sorted_values 不可為空。"""
    rank = max(1, math.ceil(q * len(sorted_values)))
    return sorted_values[rank - 1]


def measure_runtime(
    classifier: Classifier, texts: list[str], *, batch_size: int, threads: int
) -> RuntimeStats:
    """先用第一批暖機（不計時），再逐批計時；每篇耗時 = 該批耗時 / 該批篇數。"""
    if not texts:
        raise ValueError("texts is empty")
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    batches = [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]
    classifier.predict_proba(batches[0])
    batch_seconds: list[float] = []
    per_post_ms: list[float] = []
    for batch in batches:
        start = _clock()
        classifier.predict_proba(batch)
        elapsed = _clock() - start
        batch_seconds.append(elapsed)
        per_post_ms.extend([elapsed / len(batch) * 1000] * len(batch))
    batch_seconds.sort()
    per_post_ms.sort()
    return RuntimeStats(
        threads=threads,
        batch_size=batch_size,
        per_post_p50_ms=_percentile(per_post_ms, 0.5),
        per_post_p95_ms=_percentile(per_post_ms, 0.95),
        per_batch_p50_s=_percentile(batch_seconds, 0.5),
        per_batch_max_s=batch_seconds[-1],
        peak_rss_mb=_peak_rss_mb(),
    )


def _predict_in_batches(
    classifier: Classifier, texts: list[str], batch_size: int
) -> list[dict[Polarity, float]]:
    """依 batch_size 分批推論，記憶體峰值才對應 shadow 的 INFERENCE_BATCH_SIZE。"""
    if batch_size < 1:
        raise ValueError("batch_size must be >= 1")
    scores: list[dict[Polarity, float]] = []
    for i in range(0, len(texts), batch_size):
        scores.extend(classifier.predict_proba(texts[i : i + batch_size]))
    return scores


def evaluate_model(
    classifier: Classifier, examples: list[Example], *, batch_size: int = DEFAULT_BATCH_SIZE
) -> ClassificationReport:
    if not examples:
        raise ValueError("testset is empty")
    labels = [p.value for p in Polarity]
    y_true = [e.polarity.value for e in examples]
    predictions = _predict_in_batches(classifier, [e.text for e in examples], batch_size)
    y_pred = [top_class(s).value for s in predictions]
    per_class = f1_score(y_true, y_pred, labels=labels, average=None, zero_division=0)
    matrix = confusion_matrix(y_true, y_pred, labels=labels)
    return ClassificationReport(
        n=len(examples),
        macro_f1=float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)),
        per_class_f1={Polarity(lbl): float(v) for lbl, v in zip(labels, per_class, strict=True)},
        confusion={
            Polarity(t): {Polarity(p): int(matrix[i][j]) for j, p in enumerate(labels)}
            for i, t in enumerate(labels)
        },
    )


def llm_vs_human(labeler: str, llm: dict[str, Polarity], human: dict[str, Polarity]) -> Agreement:
    overlap = sorted(llm.keys() & human.keys())
    a = [llm[p] for p in overlap]
    b = [human[p] for p in overlap]
    agreed = sum(x == y for x, y in zip(a, b, strict=True))
    return Agreement(
        labeler=labeler,
        n=len(overlap),
        accuracy=agreed / len(overlap) if overlap else 0.0,
        cohen_kappa=kappa(a, b),
    )


def evaluate_by_board(
    classifier: Classifier, examples: list[Example], *, batch_size: int = DEFAULT_BATCH_SIZE
) -> dict[str, ClassificationReport]:
    """依 Example.board 分組各自評估；依看板名稱排序。"""
    groups: dict[str, list[Example]] = {}
    for e in examples:
        groups.setdefault(e.board, []).append(e)
    return {
        board: evaluate_model(classifier, groups[board], batch_size=batch_size)
        for board in sorted(groups)
    }


def agreements_by_board(
    llm_labels: dict[str, dict[str, Polarity]],
    human: dict[str, Polarity],
    boards: dict[str, str],
) -> dict[str, list[Agreement]]:
    """llm_labels 為 {labeler: {post_id: polarity}}，boards 為 {post_id: board}；依看板名稱排序。"""
    grouped: dict[str, dict[str, Polarity]] = {}
    for pid, polarity in human.items():
        if pid in boards:
            grouped.setdefault(boards[pid], {})[pid] = polarity
    return {
        board: [llm_vs_human(name, labels, grouped[board]) for name, labels in llm_labels.items()]
        for board in sorted(grouped)
    }


def render_markdown(
    model_version: str,
    model: ClassificationReport,
    agreements: list[Agreement],
    *,
    board_reports: dict[str, ClassificationReport],
    board_agreements: dict[str, list[Agreement]],
    runtime: RuntimeStats | None = None,
    label_version: str = "",
) -> str:
    """寫入 models/<model_version>/evaluation.md；手寫評估報告的數字來源（開發規格 7.11）。"""
    labels = list(Polarity)
    lines = [
        f"# 評估：{model_version}",
        "",
        f"人工測試集 {model.n} 篇（整篇情緒）。",
        "",
        "## 模型分數",
        "",
        "| 範圍 | 篇數 | macro-F1 | " + " | ".join(f"{p.value} F1" for p in labels) + " |",
        "|---" * (len(labels) + 3) + "|",
        _f1_row("整體", model),
        *(_f1_row(_board_name(b, r.n), r) for b, r in board_reports.items()),
        "",
        "整體混淆矩陣（列 = 人工，欄 = 模型）：",
        "",
        "| 人工 \\ 模型 | " + " | ".join(p.value for p in labels) + " |",
        "|---" * (len(labels) + 1) + "|",
        *(
            f"| {t.value} | " + " | ".join(str(model.confusion[t][p]) for p in labels) + " |"
            for t in labels
        ),
        "",
        "## LLM 標註者 vs 人工",
        "",
        "| 標註者 | 範圍 | 篇數 | 一致率 | Cohen's kappa |",
        "|---|---|---|---|---|",
        *(_agreement_row(a, "整體") for a in agreements if a.n > 0),
        *(
            _agreement_row(a, _board_name(board, a.n))
            for board, board_rows in board_agreements.items()
            for a in board_rows
            if a.n > 0
        ),
        "",
        *(
            f"`{a.labeler}` 在人工測試集沒有 `{label_version}` 的標註。"
            for a in agreements
            if a.n == 0
        ),
    ]
    if runtime is not None:
        lines += _runtime_section(runtime)
    return "\n".join(lines)


def _runtime_section(r: RuntimeStats) -> list[str]:
    return [
        "## CPU 推論耗時與記憶體",
        "",
        f"INFERENCE_THREADS = {r.threads}，每批 {r.batch_size} 篇。",
        "",
        "| 指標 | 數值 |",
        "|---|---|",
        f"| 每篇 p50 | {r.per_post_p50_ms:.2f} ms |",
        f"| 每篇 p95 | {r.per_post_p95_ms:.2f} ms |",
        f"| 每批 p50 | {r.per_batch_p50_s:.3f} s |",
        f"| 每批最大 | {r.per_batch_max_s:.3f} s |",
        *([f"| 載入模型後 RSS | {r.load_rss_mb:.0f} MB |"] if r.load_rss_mb is not None else []),
        f"| 記憶體峰值（RSS） | {r.peak_rss_mb:.0f} MB |",
        "",
    ]


def _board_name(board: str, n: int) -> str:
    return f"{board}（樣本少，只供參考）" if n < SMALL_BOARD_N else board


def _f1_row(scope: str, report: ClassificationReport) -> str:
    per_class = " | ".join(f"{report.per_class_f1[p]:.3f}" for p in Polarity)
    return f"| {scope} | {report.n} | **{report.macro_f1:.3f}** | {per_class} |"


def _agreement_row(a: Agreement, scope: str) -> str:
    return f"| `{a.labeler}` | {scope} | {a.n} | {a.accuracy:.1%} | {a.cohen_kappa:.3f} |"


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("evaluate")
    parser = argparse.ArgumentParser(description="在人工測試集上評估（S3-06）")
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    settings = InferenceSettings(model_dir=args.model)
    classifier, card = load_classifier(
        args.model, threads=settings.threads, max_batch_tokens=settings.max_batch_tokens
    )
    load_rss_mb = _peak_rss_mb()
    human_labels = load_human_labels(TESTSET_DIR)
    human = {
        pid: next(s.polarity for s in lbl.sentiments if s.target is None)
        for pid, lbl in human_labels.items()
    }
    ch = ClickHouseClient(ClickHouseSettings())
    try:
        posts = fetch_posts(ch, sorted(human))
        llm_labels = {
            name: fetch_whole_post_labels(ch, name, card.label_version)
            for name in (card.labeler, MANUAL_LABELER)
        }
    finally:
        ch.close()
    examples = [
        Example(
            pid,
            posts[pid].board,
            post_text(posts[pid].title, posts[pid].content, card.max_chars),
            pol,
        )
        for pid, pol in human.items()
        if pid in posts
    ]
    report = evaluate_model(classifier, examples, batch_size=settings.batch_size)
    board_reports = evaluate_by_board(classifier, examples, batch_size=settings.batch_size)
    agreements = [llm_vs_human(name, labels, human) for name, labels in llm_labels.items()]
    boards = {pid: post.board for pid, post in posts.items()}
    board_agreements = agreements_by_board(llm_labels, human, boards)

    runtime = replace(
        measure_runtime(
            classifier,
            [e.text for e in examples],
            batch_size=settings.batch_size,
            threads=settings.threads,
        ),
        load_rss_mb=load_rss_mb,
    )
    card.metrics = {
        "testset_n": float(report.n),
        "macro_f1": report.macro_f1,
        **{f"f1_{p.value}": v for p, v in report.per_class_f1.items()},
        **{f"macro_f1_{board}": r.macro_f1 for board, r in board_reports.items()},
    }
    write_card(args.model, card)
    markdown = render_markdown(
        card.model_version,
        report,
        agreements,
        board_reports=board_reports,
        board_agreements=board_agreements,
        runtime=runtime,
        label_version=card.label_version,
    )
    (args.model / REPORT_FILE).write_text(markdown)
    log.info(
        "macro-F1=%.3f on %d posts; report: %s", report.macro_f1, report.n, args.model / REPORT_FILE
    )


if __name__ == "__main__":
    main()

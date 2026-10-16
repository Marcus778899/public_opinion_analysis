"""[一次性] 在人工測試集上評估（S3-06、階段 3 驗收）。

回報 baseline 的 macro-F1 與兩個 LLM 標註者與人工的一致率，整體與各看板分開（開發規格 7.11）。
用法：python -m radar.ml.training.evaluate --model models/<model_version>
"""

import argparse
from dataclasses import dataclass
from pathlib import Path

from sklearn.metrics import confusion_matrix, f1_score
from sklearn.pipeline import Pipeline

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.log import log, setup_logging
from radar.common.settings import ClickHouseSettings
from radar.ml.labeling.cross_check import fetch_whole_post_labels, kappa
from radar.ml.labeling.manual import MANUAL_LABELER
from radar.ml.labeling.sampling import fetch_posts
from radar.ml.labeling.testset import TESTSET_DIR, load_human_labels
from radar.ml.training.dataset import Example, post_text
from radar.ml.training.train import load_model, write_card

REPORT_FILE = "evaluation.md"
# 看板樣本數低於此值時在輸出註明 F1 只供參考
SMALL_BOARD_N = 50


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


def evaluate_model(pipeline: Pipeline, examples: list[Example]) -> ClassificationReport:
    if not examples:
        raise ValueError("testset is empty")
    labels = [p.value for p in Polarity]
    y_true = [e.polarity.value for e in examples]
    y_pred = list(pipeline.predict([e.text for e in examples]))
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
    pipeline: Pipeline, examples: list[Example]
) -> dict[str, ClassificationReport]:
    """依 Example.board 分組各自評估；依看板名稱排序。"""
    groups: dict[str, list[Example]] = {}
    for e in examples:
        groups.setdefault(e.board, []).append(e)
    return {board: evaluate_model(pipeline, groups[board]) for board in sorted(groups)}


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
) -> str:
    """寫入 models/<model_version>/evaluation.md；手寫評估報告的數字來源（開發規格 7.11）。"""
    labels = list(Polarity)
    lines = [
        f"# 評估：{model_version}",
        "",
        f"人工測試集 {model.n} 篇（整篇情緒）。",
        "",
        "## Baseline",
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
        *(_agreement_row(a, "整體") for a in agreements),
        *(
            _agreement_row(a, _board_name(board, a.n))
            for board, board_rows in board_agreements.items()
            for a in board_rows
        ),
        "",
    ]
    return "\n".join(lines)


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
    pipeline, card = load_model(args.model)
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
    report = evaluate_model(pipeline, examples)
    board_reports = evaluate_by_board(pipeline, examples)
    agreements = [llm_vs_human(name, labels, human) for name, labels in llm_labels.items()]
    boards = {pid: post.board for pid, post in posts.items()}
    board_agreements = agreements_by_board(llm_labels, human, boards)

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
    )
    (args.model / REPORT_FILE).write_text(markdown)
    log.info(
        "macro-F1=%.3f on %d posts; report: %s", report.macro_f1, report.n, args.model / REPORT_FILE
    )


if __name__ == "__main__":
    main()

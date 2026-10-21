"""[一次性] 比較現行與 shadow 兩個模型版本（開發規格 7.27「比較」，S8-03）。

用法：python -m radar.ml.training.compare --a <現行版本> --b <shadow 版本> --since <UTC 時間>
產物：models/<b>/comparison.md、data/review/disagreements-<a>-vs-<b>.csv；查詢全部參數化。
"""

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from radar.common.clickhouse import ClickHouseClient
from radar.common.enums import Polarity
from radar.common.log import log, setup_logging
from radar.common.settings import InferenceRole

REVIEW_DIR = Path("data/review")
REPORT_FILE = "comparison.md"
# 信心分布的門檻（設計文件 15.8；重新決定 TELEGRAM_SENTIMENT_MIN_SCORE 用）
CONFIDENCE_THRESHOLDS = (0.4, 0.5, 0.6, 0.7)


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
    # TODO(bert-compare): posts_latest FINAL 未刪除、created_at >= since；LEFT JOIN labels
    raise NotImplementedError  # pragma: no cover（骨架）


def fetch_latency(
    client: ClickHouseClient, model_version: str, role: InferenceRole, since: datetime
) -> LatencyStats:
    # TODO(bert-compare): 表名取自 radar.ml.inference.roles.ROLE_TARGETS[role]，不由參數組出
    raise NotImplementedError  # pragma: no cover（骨架）


def agreement(pairs: list[PairedPrediction]) -> AgreementStats:
    # TODO(bert-compare)
    raise NotImplementedError  # pragma: no cover（骨架）


def confidence_buckets(scores: list[tuple[float, bool | None]]) -> list[ConfidenceBucket]:
    """scores 為 (最高分, 是否與 LLM 標註一致；沒有標註時 None)。"""
    # TODO(bert-compare)
    raise NotImplementedError  # pragma: no cover（骨架）


def render_markdown(
    a: str,
    b: str,
    overall: AgreementStats,
    by_board: dict[str, AgreementStats],
    latency: dict[str, LatencyStats],
    confidence: dict[str, list[ConfidenceBucket]],
) -> str:
    # TODO(bert-compare): 另列兩版各自對 LLM 標註的 macro-F1 與篇數
    raise NotImplementedError  # pragma: no cover（骨架）


def write_disagreements(path: Path, pairs: list[PairedPrediction]) -> int:
    """兩版 polarity 不同的列寫成 CSV，回傳列數。"""
    # TODO(bert-compare)
    raise NotImplementedError  # pragma: no cover（骨架）


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("compare")
    parser = argparse.ArgumentParser(description="比較現行與 shadow 模型（S8-03）")
    parser.add_argument("--a", required=True, help="現行版本（predictions）")
    parser.add_argument("--b", required=True, help="shadow 版本（predictions_shadow）")
    parser.add_argument("--since", type=datetime.fromisoformat, required=True)
    parser.parse_args()
    # TODO(bert-compare)
    raise NotImplementedError  # pragma: no cover（骨架）


if __name__ == "__main__":
    main()

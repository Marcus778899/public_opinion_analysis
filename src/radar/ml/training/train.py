"""[一次性] 訓練 baseline（S3-06、S3-07）：TF-IDF 字元 n-gram + Logistic Regression。

用法：python -m radar.ml.training.train --data data/datasets/<名稱>.jsonl
產物：models/<model_version>/model.joblib、model_card.json
"""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import joblib
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from radar.common.enums import Polarity
from radar.common.log import log, setup_logging
from radar.ml.training.dataset import Example, class_counts, read_jsonl

MODELS_DIR = Path("models")
MODEL_FILE = "model.joblib"
CARD_FILE = "model_card.json"
MIN_PER_CLASS = 10
PARAMS: dict[str, str | int | float] = {
    "analyzer": "char_wb",
    "ngram_min": 1,
    "ngram_max": 3,
    "min_df": 2,
    "max_features": 200_000,
    "C": 1.0,
    "class_weight": "balanced",
}


class ModelCard(BaseModel):
    model_version: str
    created_at: datetime
    dataset: str
    labeler: str
    label_version: str
    max_chars: int
    n_train: int
    class_counts: dict[str, int]
    params: dict[str, str | int | float]
    # evaluate 執行後補上
    metrics: dict[str, float] = {}


def model_version(now: datetime) -> str:
    return f"tfidf-lr-{now.astimezone(UTC):%Y%m%d%H%M}"


def build_pipeline(seed: int) -> Pipeline:
    # NOTE: 字元 n-gram 免斷詞，中文可直接用；class_weight=balanced 應付中立類偏多
    return Pipeline(
        [
            (
                "tfidf",
                TfidfVectorizer(
                    analyzer=str(PARAMS["analyzer"]),
                    ngram_range=(int(PARAMS["ngram_min"]), int(PARAMS["ngram_max"])),
                    min_df=int(PARAMS["min_df"]),
                    max_features=int(PARAMS["max_features"]),
                    sublinear_tf=True,
                ),
            ),
            (
                "clf",
                LogisticRegression(
                    C=float(PARAMS["C"]),
                    class_weight=str(PARAMS["class_weight"]),
                    max_iter=2000,
                    random_state=seed,
                ),
            ),
        ]
    )


def train(examples: list[Example], seed: int) -> Pipeline:
    counts = Counter(e.polarity for e in examples)
    too_few = [p.value for p in Polarity if counts.get(p, 0) < MIN_PER_CLASS]
    if too_few:
        raise ValueError(f"need at least {MIN_PER_CLASS} examples per class, short: {too_few}")
    pipeline = build_pipeline(seed)
    pipeline.fit([e.text for e in examples], [e.polarity.value for e in examples])
    return pipeline


def save_model(pipeline: Pipeline, card: ModelCard, models_dir: Path) -> Path:
    target = models_dir / card.model_version
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    target.mkdir(parents=True)
    joblib.dump(pipeline, target / MODEL_FILE)
    write_card(target, card)
    return target


def write_card(model_dir: Path, card: ModelCard) -> None:
    (model_dir / CARD_FILE).write_text(card.model_dump_json(indent=2))


def load_model(model_dir: Path) -> tuple[Pipeline, ModelCard]:
    # NOTE: joblib 會執行任意程式碼，只載入自己訓練的模型
    pipeline = joblib.load(model_dir / MODEL_FILE)  # nosec B301
    card = ModelCard.model_validate_json((model_dir / CARD_FILE).read_text())
    return pipeline, card


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("train")
    parser = argparse.ArgumentParser(description="訓練 TF-IDF + LR baseline（S3-06）")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    meta = json.loads(args.data.with_suffix(".meta.json").read_text())
    examples = read_jsonl(args.data)
    pipeline = train(examples, args.seed)
    now = datetime.now(UTC)
    card = ModelCard(
        model_version=model_version(now),
        created_at=now,
        dataset=meta["dataset"],
        labeler=meta["labeler"],
        label_version=meta["label_version"],
        max_chars=meta["max_chars"],
        n_train=len(examples),
        class_counts=class_counts(examples),
        params={**PARAMS, "seed": args.seed},
    )
    path = save_model(pipeline, card, MODELS_DIR)
    log.info(
        "saved %s (%d examples); next: python -m radar.ml.training.evaluate --model %s",
        path,
        len(examples),
        path,
    )


if __name__ == "__main__":
    main()

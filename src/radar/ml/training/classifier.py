"""模型載入介面（開發規格 7.27「載入」）：依 model_card.kind 回傳 sklearn 或 ONNX 實作。

evaluate 與推論服務只透過 Classifier 呼叫模型，不直接碰 Pipeline 或 onnxruntime。
"""

from pathlib import Path
from typing import Protocol

from sklearn.pipeline import Pipeline

from radar.common.enums import Polarity
from radar.ml.training.train import ModelCard

ONNX_MODEL_FILE = "model.onnx"
TOKENIZER_FILE = "tokenizer.json"


class Classifier(Protocol):
    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        """每篇一個 dict：三類齊全、總和為 1；texts 為空時回傳空 list。"""
        ...


def top_class(scores: dict[Polarity, float]) -> Polarity:
    """最高分的類別；同分時取 Polarity 宣告順序的第一個。"""
    # TODO(bert-classifier): 與 inference/main.py 現行 predict() 的取法一致
    raise NotImplementedError  # pragma: no cover（骨架）


class SklearnClassifier:
    """包裝本機訓練的 baseline；模型缺某一類時該類補 0（原 inference/main.py 的 predict）。"""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        # TODO(bert-classifier): 搬入 inference/main.py predict() 的缺類補 0
        raise NotImplementedError  # pragma: no cover（骨架）


class OnnxClassifier:
    """tokenizer 截斷到 max_len、batch 內 padding；logits 依 labels 順序做 softmax。"""

    def __init__(self, model_dir: Path, card: ModelCard, threads: int) -> None:
        # TODO(bert-classifier): onnxruntime.InferenceSession（intra_op_num_threads=threads）
        # 與 tokenizers.Tokenizer.from_file；模型有 token_type_ids 輸入時一併餵（全 0）
        raise NotImplementedError  # pragma: no cover（骨架）

    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        # TODO(bert-classifier)
        raise NotImplementedError  # pragma: no cover（骨架）


def load_classifier(model_dir: Path, *, threads: int) -> tuple[Classifier, ModelCard]:
    """讀 model_card.json，依 kind 建立實作；threads 只用於 ONNX（INFERENCE_THREADS）。"""
    # TODO(bert-classifier): sklearn 走 train.load_model（joblib 只用於本機訓練的 baseline）
    raise NotImplementedError  # pragma: no cover（骨架）

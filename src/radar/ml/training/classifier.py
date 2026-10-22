"""模型載入介面（開發規格 7.27「載入」）：依 model_card.kind 回傳 sklearn 或 ONNX 實作。

evaluate 與推論服務只透過 Classifier 呼叫模型，不直接碰 Pipeline 或 onnxruntime。
"""

from pathlib import Path
from typing import Protocol

import numpy as np
import onnxruntime
from sklearn.pipeline import Pipeline
from tokenizers import Tokenizer

from radar.common.enums import Polarity
from radar.ml.training.train import CARD_FILE, ModelCard, ModelKind, load_model

ONNX_MODEL_FILE = "model.onnx"
TOKENIZER_FILE = "tokenizer.json"


class Classifier(Protocol):
    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        """每篇一個 dict：三類齊全、總和為 1；texts 為空時回傳空 list。"""
        ...


PAD_TOKEN = "[PAD]"


def top_class(scores: dict[Polarity, float]) -> Polarity:
    """最高分的類別；同分時取 Polarity 宣告順序的第一個。"""
    return max(Polarity, key=lambda c: scores[c])


class SklearnClassifier:
    """包裝本機訓練的 baseline；模型缺某一類時該類補 0（原 inference/main.py 的 predict）。"""

    def __init__(self, pipeline: Pipeline) -> None:
        self._pipeline = pipeline

    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        if not texts:
            return []
        classes = [Polarity(c) for c in self._pipeline.classes_]
        results: list[dict[Polarity, float]] = []
        for row in self._pipeline.predict_proba(texts):
            # NOTE: 訓練資料缺某一類時模型沒有該類，分數記 0，訊息仍帶齊三類（開發規格 3.5）
            scores = dict.fromkeys(Polarity, 0.0)
            scores.update({c: float(p) for c, p in zip(classes, row, strict=True)})
            results.append(scores)
        return results


class OnnxClassifier:
    """tokenizer 截斷到 max_len、batch 內 padding；logits 依 labels 順序做 softmax。"""

    def __init__(self, model_dir: Path, card: ModelCard, threads: int) -> None:
        if card.max_len is None:
            raise ValueError("onnx model card needs max_len")
        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = threads
        self._session = onnxruntime.InferenceSession(
            str(model_dir / ONNX_MODEL_FILE),
            options,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {i.name for i in self._session.get_inputs()}
        self._labels = list(card.labels)
        self._tokenizer = Tokenizer.from_file(str(model_dir / TOKENIZER_FILE))
        self._tokenizer.enable_truncation(max_length=card.max_len)
        pad_id = self._tokenizer.token_to_id(PAD_TOKEN) or 0
        self._tokenizer.enable_padding(pad_id=pad_id, pad_token=PAD_TOKEN)

    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        if not texts:
            return []
        encodings = self._tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        feeds = {
            "input_ids": ids,
            "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
        }
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        logits = self._session.run(["logits"], feeds)[0].astype(np.float64)
        shifted = np.exp(logits - logits.max(axis=1, keepdims=True))
        probs = shifted / shifted.sum(axis=1, keepdims=True)
        return [
            {label: float(p) for label, p in zip(self._labels, row, strict=True)} for row in probs
        ]


def load_classifier(model_dir: Path, *, threads: int) -> tuple[Classifier, ModelCard]:
    """讀 model_card.json，依 kind 建立實作；threads 只用於 ONNX（INFERENCE_THREADS）。"""
    card = ModelCard.model_validate_json((model_dir / CARD_FILE).read_text())
    if card.kind is ModelKind.ONNX:
        return OnnxClassifier(model_dir, card, threads), card
    pipeline, card = load_model(model_dir)
    return SklearnClassifier(pipeline), card

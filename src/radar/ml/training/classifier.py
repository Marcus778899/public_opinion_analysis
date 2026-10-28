"""模型載入介面（開發規格 7.27「載入」）：依 model_card.kind 回傳 sklearn 或 ONNX 實作。

evaluate 與推論服務只透過 Classifier 呼叫模型，不直接碰 Pipeline 或 onnxruntime。
"""

from pathlib import Path
from typing import Protocol

import numpy as np
import onnxruntime
from sklearn.pipeline import Pipeline
from tokenizers import Encoding, Tokenizer

from radar.common.enums import Polarity
from radar.ml.training.train import CARD_FILE, ModelCard, ModelKind, load_model

ONNX_MODEL_FILE = "model.onnx"
TOKENIZER_FILE = "tokenizer.json"


class Classifier(Protocol):
    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        """每篇一個 dict：三類齊全、總和為 1；texts 為空時回傳空 list。"""
        ...


PAD_TOKEN = "[PAD]"
DEFAULT_MAX_BATCH_TOKENS = 4096


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
    """截斷到 max_len、依長度排序切批（篇數 × 序列長度 ≤ 上限）；logits 依 labels 做 softmax。"""

    def __init__(
        self,
        model_dir: Path,
        card: ModelCard,
        threads: int,
        max_batch_tokens: int = DEFAULT_MAX_BATCH_TOKENS,
    ) -> None:
        if card.max_len is None:
            raise ValueError("onnx model card needs max_len")
        if max_batch_tokens < card.max_len:
            raise ValueError(f"max_batch_tokens {max_batch_tokens} < max_len {card.max_len}")
        self._max_batch_tokens = max_batch_tokens
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
        # NOTE: 不用 tokenizer 的 padding（會補到整批最長）；各小批自己補
        self._pad_id = self._tokenizer.token_to_id(PAD_TOKEN) or 0

    def predict_proba(self, texts: list[str]) -> list[dict[Polarity, float]]:
        if not texts:
            return []
        encodings = self._tokenizer.encode_batch(texts)
        order = sorted(range(len(texts)), key=lambda i: len(encodings[i].ids))
        results: list[dict[Polarity, float] | None] = [None] * len(texts)
        for chunk in self._chunks(order, [len(e.ids) for e in encodings]):
            probs = self._run([encodings[i] for i in chunk])
            for i, row in zip(chunk, probs, strict=True):
                results[i] = {label: float(p) for label, p in zip(self._labels, row, strict=True)}
        return [r for r in results if r is not None]

    def _chunks(self, order: list[int], lengths: list[int]) -> list[list[int]]:
        # order 依長度遞增，新增一篇後的序列長度就是該篇長度
        chunks: list[list[int]] = []
        current: list[int] = []
        for i in order:
            if current and (len(current) + 1) * max(lengths[i], 1) > self._max_batch_tokens:
                chunks.append(current)
                current = []
            current.append(i)
        if current:
            chunks.append(current)
        return chunks

    def _run(self, encodings: list[Encoding]) -> np.ndarray:
        width = max(max(len(e.ids) for e in encodings), 1)
        ids = np.full((len(encodings), width), self._pad_id, dtype=np.int64)
        mask = np.zeros((len(encodings), width), dtype=np.int64)
        for row, e in enumerate(encodings):
            ids[row, : len(e.ids)] = e.ids
            mask[row, : len(e.ids)] = 1
        feeds = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self._input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        logits = self._session.run(["logits"], feeds)[0].astype(np.float64)
        shifted = np.exp(logits - logits.max(axis=1, keepdims=True))
        return shifted / shifted.sum(axis=1, keepdims=True)


def load_classifier(
    model_dir: Path, *, threads: int, max_batch_tokens: int = DEFAULT_MAX_BATCH_TOKENS
) -> tuple[Classifier, ModelCard]:
    """讀 model_card.json，依 kind 建立實作；threads、max_batch_tokens 只用於 ONNX。"""
    card = ModelCard.model_validate_json((model_dir / CARD_FILE).read_text())
    if card.kind is ModelKind.ONNX:
        return OnnxClassifier(model_dir, card, threads, max_batch_tokens), card
    pipeline, card = load_model(model_dir)
    return SklearnClassifier(pipeline), card

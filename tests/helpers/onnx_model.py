"""測試用的小 BERT 替身（開發規格 7.27「測試」）：tokenizer、fp32／int8 ONNX、模型包 zip。

模型 = 詞向量 → 依 attention_mask 平均 → 線性層，輸入輸出同「模型包格式」；
關鍵字決定類別（POSITIVE_WORDS…），padding 不影響結果。檔案都寫在呼叫端給的資料夾。
"""

import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import onnx
from onnx import TensorProto, helper, numpy_helper
from onnxruntime.quantization import QuantType, quantize_dynamic
from tokenizers import Tokenizer
from tokenizers.models import WordPiece
from tokenizers.normalizers import BertNormalizer
from tokenizers.pre_tokenizers import BertPreTokenizer
from tokenizers.processors import TemplateProcessing

from radar.common.enums import Polarity
from radar.ml.training.train import ModelCard

MODEL_FILE = "model.onnx"
TOKENIZER_FILE = "tokenizer.json"
CARD_FILE = "model_card.json"
PACKAGE_FILES = (MODEL_FILE, TOKENIZER_FILE, CARD_FILE)

SPECIAL_TOKENS = ("[PAD]", "[UNK]", "[CLS]", "[SEP]")
PAD_ID = 0
POSITIVE_WORDS = ("好", "棒", "讚", "漲")
NEGATIVE_WORDS = ("爛", "糟", "慘", "崩")
NEUTRAL_WORDS = ("的", "今", "天", "請", "問", "公", "告")
CLASS_WORDS: dict[Polarity, tuple[str, ...]] = {
    Polarity.POSITIVE: POSITIVE_WORDS,
    Polarity.NEGATIVE: NEGATIVE_WORDS,
    Polarity.NEUTRAL: NEUTRAL_WORDS,
}
VOCAB: tuple[str, ...] = (*SPECIAL_TOKENS, *POSITIVE_WORDS, *NEGATIVE_WORDS, *NEUTRAL_WORDS)
DEFAULT_LABELS: tuple[Polarity, ...] = tuple(Polarity)
OPSET = 17
# NOTE: onnx 新版預設的 IR 版本可能比 onnxruntime 支援的新，固定在 opset 17 對應的 8
IR_VERSION = 8
HIDDEN = 4
# 正負面詞的權重大於中立詞：「今天好棒」判為正面；只有特殊字元或未知字時判為中立
POLAR_WEIGHT = 4.0
NEUTRAL_WEIGHT = 1.0


def build_tokenizer() -> Tokenizer:
    """BERT 式 WordPiece：中文逐字切、前後加 [CLS]/[SEP]；不設 truncation 與 padding。"""
    vocab = {token: i for i, token in enumerate(VOCAB)}
    tokenizer = Tokenizer(WordPiece(vocab, unk_token="[UNK]"))
    tokenizer.normalizer = BertNormalizer(handle_chinese_chars=True, lowercase=True)
    tokenizer.pre_tokenizer = BertPreTokenizer()
    tokenizer.post_processor = TemplateProcessing(
        single="[CLS] $A [SEP]",
        pair="[CLS] $A [SEP] $B:1 [SEP]:1",
        special_tokens=[("[CLS]", vocab["[CLS]"]), ("[SEP]", vocab["[SEP]"])],
    )
    return tokenizer


def write_tokenizer(path: Path) -> Path:
    build_tokenizer().save(str(path))
    return path


@dataclass(frozen=True)
class TinyWeights:
    embedding: np.ndarray  # [vocab, HIDDEN]
    token_type_embedding: np.ndarray  # [2, HIDDEN]
    weight: np.ndarray  # [HIDDEN, n_labels]
    bias: np.ndarray  # [n_labels]


def tiny_weights(labels: tuple[Polarity, ...] = DEFAULT_LABELS) -> TinyWeights:
    """第 i 維代表 labels[i]；線性層把維度對到 logits 的位置，labels 換順序結果仍一致。"""
    n = len(labels)
    embedding = np.zeros((len(VOCAB), HIDDEN), dtype=np.float32)
    neutral_dim = labels.index(Polarity.NEUTRAL)
    for special in ("[UNK]", "[CLS]", "[SEP]"):
        embedding[VOCAB.index(special), neutral_dim] = NEUTRAL_WEIGHT
    for polarity, words in CLASS_WORDS.items():
        value = NEUTRAL_WEIGHT if polarity is Polarity.NEUTRAL else POLAR_WEIGHT
        for word in words:
            embedding[VOCAB.index(word), labels.index(polarity)] = value
    weight = np.zeros((HIDDEN, n), dtype=np.float32)
    weight[:n, :n] = np.eye(n, dtype=np.float32)
    # NOTE: token type 的向量刻意非 0，才測得出推論端有沒有把 token_type_ids 傳進去
    token_type_embedding = np.zeros((2, HIDDEN), dtype=np.float32)
    token_type_embedding[1, labels.index(Polarity.NEGATIVE)] = POLAR_WEIGHT
    return TinyWeights(embedding, token_type_embedding, weight, np.zeros(n, dtype=np.float32))


def reference_logits(
    weights: TinyWeights,
    input_ids: np.ndarray,
    attention_mask: np.ndarray,
    token_type_ids: np.ndarray | None = None,
) -> np.ndarray:
    """與 fp32 ONNX 相同的計算（numpy），供測試比對。"""
    hidden = weights.embedding[input_ids]
    if token_type_ids is not None:
        hidden = hidden + weights.token_type_embedding[token_type_ids]
    mask = attention_mask.astype(np.float32)[..., None]
    pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1.0)
    return pooled @ weights.weight + weights.bias


def _graph(weights: TinyWeights, with_token_type_ids: bool) -> onnx.ModelProto:
    n_labels = weights.weight.shape[1]
    dims = ["batch", "seq"]
    inputs = [
        helper.make_tensor_value_info("input_ids", TensorProto.INT64, dims),
        helper.make_tensor_value_info("attention_mask", TensorProto.INT64, dims),
    ]
    initializers = [
        numpy_helper.from_array(weights.embedding, "embedding"),
        numpy_helper.from_array(weights.weight, "classifier_weight"),
        numpy_helper.from_array(weights.bias, "classifier_bias"),
        numpy_helper.from_array(np.array([-1], dtype=np.int64), "last_axis"),
        numpy_helper.from_array(np.array([1], dtype=np.int64), "seq_axis"),
        numpy_helper.from_array(np.array(1.0, dtype=np.float32), "one"),
    ]
    nodes = [helper.make_node("Gather", ["embedding", "input_ids"], ["word_hidden"])]
    hidden = "word_hidden"
    if with_token_type_ids:
        inputs.append(helper.make_tensor_value_info("token_type_ids", TensorProto.INT64, dims))
        initializers.append(
            numpy_helper.from_array(weights.token_type_embedding, "token_type_embedding")
        )
        nodes += [
            helper.make_node("Gather", ["token_type_embedding", "token_type_ids"], ["type_hidden"]),
            helper.make_node("Add", ["word_hidden", "type_hidden"], ["hidden"]),
        ]
        hidden = "hidden"
    nodes += [
        helper.make_node("Cast", ["attention_mask"], ["mask_f"], to=TensorProto.FLOAT),
        helper.make_node("Unsqueeze", ["mask_f", "last_axis"], ["mask_3d"]),
        helper.make_node("Mul", [hidden, "mask_3d"], ["masked"]),
        helper.make_node("ReduceSum", ["masked", "seq_axis"], ["summed"], keepdims=0),
        helper.make_node("ReduceSum", ["mask_3d", "seq_axis"], ["count"], keepdims=0),
        helper.make_node("Max", ["count", "one"], ["safe_count"]),
        helper.make_node("Div", ["summed", "safe_count"], ["pooled"]),
        helper.make_node("MatMul", ["pooled", "classifier_weight"], ["projected"]),
        helper.make_node("Add", ["projected", "classifier_bias"], ["logits"]),
    ]
    output = helper.make_tensor_value_info("logits", TensorProto.FLOAT, ["batch", n_labels])
    graph = helper.make_graph(nodes, "tiny_bert", inputs, [output], initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", OPSET)])
    model.ir_version = IR_VERSION
    onnx.checker.check_model(model)
    return model


def write_onnx_model(
    path: Path,
    *,
    labels: tuple[Polarity, ...] = DEFAULT_LABELS,
    quantized: bool = False,
    with_token_type_ids: bool = False,
) -> Path:
    """寫出 fp32，或再以 onnxruntime 動態量化成 int8（與 notebook 的量化方式同類）。"""
    model = _graph(tiny_weights(labels), with_token_type_ids)
    if not quantized:
        onnx.save(model, str(path))
        return path
    fp32_path = path.with_name(f"{path.stem}.fp32.onnx")
    onnx.save(model, str(fp32_path))
    quantize_dynamic(fp32_path, path, weight_type=QuantType.QInt8, op_types_to_quantize=["MatMul"])
    fp32_path.unlink()
    return path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def model_version_for(quantized: bool, base: str = "test", stamp: str = "202610210000") -> str:
    """命名同 notebook：bert-<預訓練簡稱>-<UTC yyyymmddHHMM>，int8 加 -int8（開發規格 7.27）。"""
    version = f"bert-{base}-{stamp}"
    return f"{version}-int8" if quantized else version


def make_card(
    files: dict[str, str],
    *,
    model_version: str,
    labels: tuple[Polarity, ...] = DEFAULT_LABELS,
    max_len: int = 32,
    max_chars: int = 2000,
    base_model: str = "test/tiny-bert@0000000",
) -> ModelCard:
    return ModelCard(
        model_version=model_version,
        created_at=datetime(2026, 10, 21, tzinfo=UTC),
        dataset="test-dataset",
        labeler="groq",
        label_version="test",
        max_chars=max_chars,
        n_train=0,
        class_counts={},
        params={},
        kind="onnx",
        base_model=base_model,
        max_len=max_len,
        labels=list(labels),
        files=files,
    )


def package_members(
    work_dir: Path,
    *,
    quantized: bool = False,
    labels: tuple[Polarity, ...] = DEFAULT_LABELS,
    with_token_type_ids: bool = False,
    model_version: str | None = None,
    max_len: int = 32,
    max_chars: int = 2000,
) -> dict[str, bytes]:
    """模型包的三個檔（檔名 → 內容），card 的 files 為另外兩檔的 SHA-256；測試可改內容再打包。"""
    work_dir.mkdir(parents=True, exist_ok=True)
    model_path = write_onnx_model(
        work_dir / MODEL_FILE,
        labels=labels,
        quantized=quantized,
        with_token_type_ids=with_token_type_ids,
    )
    tokenizer_path = write_tokenizer(work_dir / TOKENIZER_FILE)
    members = {MODEL_FILE: model_path.read_bytes(), TOKENIZER_FILE: tokenizer_path.read_bytes()}
    card = make_card(
        {name: sha256_bytes(data) for name, data in members.items()},
        model_version=model_version or model_version_for(quantized),
        labels=labels,
        max_len=max_len,
        max_chars=max_chars,
    )
    members[CARD_FILE] = card.model_dump_json(indent=2).encode()
    return members


def write_zip(path: Path, members: dict[str, bytes]) -> Path:
    """依給定的名稱寫入（可含 ../ 等惡意路徑，供 import 的拒絕測試用）。"""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def build_model_dir(model_dir: Path, **kwargs: object) -> Path:
    """直接寫成 import 後的 models/<model_version>/ 樣子（kwargs 同 package_members）。"""
    members = package_members(model_dir, **kwargs)  # type: ignore[arg-type]
    for name, data in members.items():
        (model_dir / name).write_bytes(data)
    return model_dir


def build_model_package(out_dir: Path, **kwargs: object) -> Path:
    """回傳模型包 zip：<out_dir>/<model_version>.zip（kwargs 同 package_members）。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    work = out_dir / "_build"
    members = package_members(work, **kwargs)  # type: ignore[arg-type]
    version = ModelCard.model_validate_json(members[CARD_FILE]).model_version
    for name in PACKAGE_FILES:
        (work / name).unlink(missing_ok=True)
    work.rmdir()
    return write_zip(out_dir / f"{version}.zip", members)


def read_zip(path: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as zf:
        return {name: zf.read(name) for name in zf.namelist()}

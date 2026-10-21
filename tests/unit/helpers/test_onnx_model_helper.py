import json

import numpy as np
import onnx
import onnxruntime as ort
import pytest
from tokenizers import Tokenizer

from radar.common.enums import Polarity
from radar.ml.training.train import ModelCard, ModelKind
from tests.helpers.onnx_model import (
    CARD_FILE,
    DEFAULT_LABELS,
    MODEL_FILE,
    PACKAGE_FILES,
    PAD_ID,
    TOKENIZER_FILE,
    build_model_dir,
    build_model_package,
    build_tokenizer,
    model_version_for,
    package_members,
    read_zip,
    reference_logits,
    sha256_bytes,
    sha256_file,
    tiny_weights,
    write_onnx_model,
    write_tokenizer,
    write_zip,
)

TEXTS = ["今天好棒", "爛透了糟糕", "請問公告", "???"]
EXPECTED = [Polarity.POSITIVE, Polarity.NEGATIVE, Polarity.NEUTRAL, Polarity.NEUTRAL]


def encode(tokenizer: Tokenizer, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    tokenizer.enable_padding(pad_id=PAD_ID, pad_token="[PAD]")
    encodings = tokenizer.encode_batch(texts)
    ids = np.array([e.ids for e in encodings], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
    return ids, mask


def run(path, feed: dict[str, np.ndarray]) -> np.ndarray:
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    return session.run(["logits"], feed)[0]


def predicted(logits: np.ndarray, labels: tuple[Polarity, ...]) -> list[Polarity]:
    return [labels[i] for i in logits.argmax(axis=1)]


# ---- tokenizer ----


def test_tokenizer_splits_chinese_per_char_and_adds_cls_sep():
    encoding = build_tokenizer().encode("今天好棒")

    assert encoding.tokens == ["[CLS]", "今", "天", "好", "棒", "[SEP]"]


def test_tokenizer_unknown_chars_map_to_unk():
    assert build_tokenizer().encode("嗨").tokens == ["[CLS]", "[UNK]", "[SEP]"]


def test_tokenizer_saved_json_reloads_with_same_ids_and_no_truncation(tmp_path):
    path = write_tokenizer(tmp_path / TOKENIZER_FILE)

    loaded = Tokenizer.from_file(str(path))

    assert loaded.encode("今天好棒").ids == build_tokenizer().encode("今天好棒").ids
    assert loaded.truncation is None and loaded.padding is None
    assert len(loaded.encode("好" * 600).ids) == 602


# ---- fp32 小模型 ----


def test_fp32_model_has_bundle_format_inputs_and_dynamic_axes(tmp_path):
    path = write_onnx_model(tmp_path / MODEL_FILE)
    session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])

    inputs = {i.name: (i.type, i.shape) for i in session.get_inputs()}
    outputs = {o.name: (o.type, o.shape) for o in session.get_outputs()}

    assert inputs == {
        "input_ids": ("tensor(int64)", ["batch", "seq"]),
        "attention_mask": ("tensor(int64)", ["batch", "seq"]),
    }
    assert outputs == {"logits": ("tensor(float)", ["batch", 3])}


def test_fp32_model_matches_numpy_reference_and_keyword_classes(tmp_path):
    path = write_onnx_model(tmp_path / MODEL_FILE)
    ids, mask = encode(build_tokenizer(), TEXTS)

    logits = run(path, {"input_ids": ids, "attention_mask": mask})

    np.testing.assert_allclose(logits, reference_logits(tiny_weights(), ids, mask), atol=1e-6)
    assert predicted(logits, DEFAULT_LABELS) == EXPECTED


def test_fp32_model_padding_does_not_change_logits(tmp_path):
    path = write_onnx_model(tmp_path / MODEL_FILE)
    tokenizer = build_tokenizer()
    alone_ids, alone_mask = encode(tokenizer, ["好"])
    batch_ids, batch_mask = encode(tokenizer, ["好", "今天天氣請問公告的"])

    alone = run(path, {"input_ids": alone_ids, "attention_mask": alone_mask})
    batched = run(path, {"input_ids": batch_ids, "attention_mask": batch_mask})

    assert batch_ids.shape[1] > alone_ids.shape[1]
    np.testing.assert_allclose(batched[0], alone[0], atol=1e-6)


def test_custom_label_order_permutes_logits_but_keeps_classes(tmp_path):
    labels = (Polarity.NEUTRAL, Polarity.POSITIVE, Polarity.NEGATIVE)
    path = write_onnx_model(tmp_path / MODEL_FILE, labels=labels)
    ids, mask = encode(build_tokenizer(), TEXTS)

    logits = run(path, {"input_ids": ids, "attention_mask": mask})

    assert predicted(logits, labels) == EXPECTED
    assert predicted(logits, DEFAULT_LABELS) != EXPECTED


def test_token_type_ids_variant_requires_and_uses_third_input(tmp_path):
    path = write_onnx_model(tmp_path / MODEL_FILE, with_token_type_ids=True)
    ids, mask = encode(build_tokenizer(), ["今天好棒"])

    zeros = run(path, {"input_ids": ids, "attention_mask": mask, "token_type_ids": ids * 0})
    ones = run(path, {"input_ids": ids, "attention_mask": mask, "token_type_ids": ids * 0 + 1})

    assert predicted(zeros, DEFAULT_LABELS) == [Polarity.POSITIVE]
    assert not np.allclose(zeros, ones)
    with pytest.raises(ValueError, match="token_type_ids"):
        run(path, {"input_ids": ids, "attention_mask": mask})


# ---- int8 小模型 ----


def test_int8_model_is_dynamically_quantized_and_agrees_with_fp32(tmp_path):
    fp32 = write_onnx_model(tmp_path / "fp32.onnx")
    int8 = write_onnx_model(tmp_path / MODEL_FILE, quantized=True)
    ids, mask = encode(build_tokenizer(), TEXTS)

    feed = {"input_ids": ids, "attention_mask": mask}
    ops = {node.op_type for node in onnx.load(str(int8)).graph.node}

    assert {"DynamicQuantizeLinear", "MatMulInteger"} <= ops
    assert predicted(run(int8, feed), DEFAULT_LABELS) == EXPECTED
    np.testing.assert_allclose(run(int8, feed), run(fp32, feed), atol=0.05)
    assert not (tmp_path / "model.fp32.onnx").exists()


# ---- 模型包 ----


def test_model_version_naming_matches_notebook_convention():
    assert model_version_for(False, base="macbert") == "bert-macbert-202610210000"
    assert model_version_for(True, base="ckip") == "bert-ckip-202610210000-int8"


@pytest.mark.parametrize("quantized", [False, True])
def test_package_zip_has_exactly_three_files_with_matching_card_hashes(tmp_path, quantized):
    path = build_model_package(tmp_path / "out", quantized=quantized)

    members = read_zip(path)
    card = ModelCard.model_validate_json(members[CARD_FILE])

    assert sorted(members) == sorted(PACKAGE_FILES)
    assert path.name == f"{card.model_version}.zip"
    assert card.kind is ModelKind.ONNX
    assert card.files == {
        MODEL_FILE: sha256_bytes(members[MODEL_FILE]),
        TOKENIZER_FILE: sha256_bytes(members[TOKENIZER_FILE]),
    }
    assert card.model_version.endswith("-int8") == quantized
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == [path.name]


def test_package_members_card_records_labels_and_lengths(tmp_path):
    labels = (Polarity.NEGATIVE, Polarity.NEUTRAL, Polarity.POSITIVE)

    members = package_members(tmp_path, labels=labels, max_len=16, max_chars=100)

    card = json.loads(members[CARD_FILE])
    assert card["labels"] == ["negative", "neutral", "positive"]
    assert (card["max_len"], card["max_chars"]) == (16, 100)
    assert card["base_model"]


def test_tampered_member_no_longer_matches_card_hash(tmp_path):
    members = package_members(tmp_path)
    card = ModelCard.model_validate_json(members[CARD_FILE])

    members[TOKENIZER_FILE] += b" "
    path = write_zip(tmp_path / "bad.zip", members)

    assert sha256_bytes(read_zip(path)[TOKENIZER_FILE]) != card.files[TOKENIZER_FILE]


def test_write_zip_keeps_given_names_for_rejection_tests(tmp_path):
    path = write_zip(tmp_path / "evil.zip", {"../escape.onnx": b"x", "extra.bin": b"y"})

    assert sorted(read_zip(path)) == ["../escape.onnx", "extra.bin"]


def test_build_model_dir_writes_imported_layout(tmp_path):
    model_dir = build_model_dir(tmp_path / "bert-test-202610210000", quantized=True)

    card = ModelCard.model_validate_json((model_dir / CARD_FILE).read_text())

    assert sorted(p.name for p in model_dir.iterdir()) == sorted(PACKAGE_FILES)
    assert card.files[MODEL_FILE] == sha256_file(model_dir / MODEL_FILE)

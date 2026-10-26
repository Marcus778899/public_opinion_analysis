"""bert-notebook 驗收測試（開發規格 7.27；D-021、D-022、D-024、D-025 定案 B）。

notebook 不在 CI 執行，這裡只對原始碼做靜態檢查（json 解析、ast、正規表示式），
不下載模型、不連網。
"""

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest

from radar.common.enums import Polarity
from radar.ml.training.train import ModelCard

NOTEBOOK = Path(__file__).resolve().parents[4] / "notebooks" / "bert_finetune.ipynb"

MACBERT_REV = "a986e004d2a7f2a1c2f5a3edef4e20604a974ed1"
CKIP_PR_COMMIT = "d3e55b839fccbf1bba9e194b8626b18b30fcc5f3"
GOOGLE_TOKENIZER_REV = "8f23c25b06e129b6c986331a13d8d025a92cf0ea"


@pytest.fixture(scope="module")
def nb() -> dict[str, Any]:
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def code_cells(nb: dict[str, Any]) -> list[str]:
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]


@pytest.fixture(scope="module")
def first(code_cells: list[str]) -> str:
    assert code_cells, "notebook 沒有程式格"
    return code_cells[0]


@pytest.fixture(scope="module")
def source(code_cells: list[str]) -> str:
    return "\n".join(code_cells)


def _parse(cell: str) -> ast.Module:
    # 魔術指令與 shell 行不是 Python，先去掉
    lines = [("" if ln.lstrip().startswith(("!", "%")) else ln) for ln in cell.splitlines()]
    return ast.parse("\n".join(lines))


def _string_constants(source: str) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(_parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            out.add(node.value)
    return out


# --- 沒有輸出、不依賴 radar、無 TODO ---


def test_notebook_is_valid_nbformat4_json(nb: dict[str, Any]) -> None:
    assert nb["nbformat"] == 4
    assert all("source" in c for c in nb["cells"])


def test_code_cells_have_no_outputs_nor_execution_count(nb: dict[str, Any]) -> None:
    for cell in nb["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == []
            assert cell["execution_count"] is None


def test_notebook_has_no_todo_marker_for_this_task() -> None:
    assert "TODO(bert-notebook)" not in NOTEBOOK.read_text(encoding="utf-8")


def test_notebook_does_not_import_radar(source: str) -> None:
    assert not re.search(r"^\s*(import|from)\s+radar\b", source, re.M)


def test_notebook_has_no_token_nor_drive_mount(source: str) -> None:
    assert not re.search(r"hf_[A-Za-z0-9]{20,}", source)
    assert not re.search(r"(HF_TOKEN|HUGGING_?FACE_HUB_TOKEN)\s*=\s*[\"'][^\"']", source)
    assert "drive.mount" not in source  # D-024


# --- 與 radar 定義一致：類別順序、model_card 欄位 ---


def test_notebook_label_order_matches_polarity_definition(source: str) -> None:
    expected = [p.value for p in Polarity]
    lists = []
    for node in ast.walk(_parse(source)):
        if (
            isinstance(node, ast.List)
            and node.elts
            and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts)
        ):
            lists.append([e.value for e in node.elts])  # type: ignore[attr-defined]
    label_lists = [lst for lst in lists if set(lst) == set(expected)]
    assert label_lists, "notebook 沒有三類別清單"
    assert all(lst == expected for lst in label_lists)


def test_notebook_model_card_has_every_radar_field(source: str) -> None:
    consts = _string_constants(source)
    missing = [f for f in ModelCard.model_fields if f != "metrics" and f not in consts]
    assert not missing, f"model_card 缺欄位: {missing}"
    assert "onnx" in consts  # kind


def test_notebook_card_records_base_model_and_tokenizer_with_revision(source: str) -> None:
    assert re.search(r"base_model[^\n]*@|@[^\n]*base_model", source) or "@{" in source
    assert re.search(r"tokenizer[^\n]*@", source, re.I)


def test_model_version_follows_naming_with_base_and_utc_timestamp(source: str) -> None:
    assert re.search(r"bert-\{BASE\}-", source)
    assert "%Y%m%d%H%M" in source
    assert "-int8" in source
    assert "utc" in source.lower()


# --- 第一格 ---


def test_first_cell_defines_base_param_with_both_options(first: str) -> None:
    assert re.search(r"^BASE\s*=\s*[\"'](macbert|ckip)[\"']", first, re.M)
    assert '"macbert"' in first or "'macbert'" in first
    assert '"ckip"' in first or "'ckip'" in first
    assert "hfl/chinese-macbert-base" in first
    assert "ckiplab/bert-base-chinese" in first


def test_first_cell_pins_revisions_including_ckip_safetensors_pr_and_google_tokenizer(
    first: str,
) -> None:
    assert MACBERT_REV in first
    assert CKIP_PR_COMMIT in first
    assert "refs/pr/1" in first
    assert "google-bert/bert-base-chinese" in first
    assert GOOGLE_TOKENIZER_REV in first


def test_first_cell_does_not_pin_ckip_to_main_revision(first: str) -> None:
    # D-025 B：ckip 權重不可再用只有 pytorch_model.bin 的 main
    assert "efe27bb4a9373384e0120ffe1cf327714ceb61bf" not in first


def test_first_cell_pins_package_versions(first: str) -> None:
    for pkg in ("torch", "transformers", "optimum"):
        assert re.search(rf"{pkg}(\[[a-z]+\])?==\d", first), f"{pkg} 未釘版本"


def test_first_cell_checks_torch_at_least_2_6_and_stops(first: str) -> None:
    assert "2.6" in first
    assert "torch" in first
    assert re.search(r"\braise\b|sys\.exit|\bassert\b", first)


def test_first_cell_stops_when_revision_is_still_placeholder(first: str) -> None:
    assert re.search(r"<revision>|startswith\(\s*[\"']<|placeholder|佔位", first, re.I)
    assert re.search(r"\braise\b|sys\.exit|\bassert\b", first)
    for rev in (MACBERT_REV, CKIP_PR_COMMIT, GOOGLE_TOKENIZER_REV):
        assert re.fullmatch(r"[0-9a-f]{40}", rev)


def test_first_cell_defaults_max_len_512_and_seed_42(first: str) -> None:
    assert re.search(r"^MAX_LEN\s*=\s*512\b", first, re.M)
    assert re.search(r"^SEED\s*=\s*42\b", first, re.M)


# --- 載入權重 ---


def test_ckip_loads_safetensors_only_and_macbert_loads_bin(source: str) -> None:
    assert "use_safetensors=True" in source
    assert "use_safetensors=False" in source


def test_trust_remote_code_is_always_false(source: str) -> None:
    assert "trust_remote_code=False" in source
    assert "trust_remote_code=True" not in source
    assert not re.search(r"trust_remote_code\s*=\s*[^F\s]", source)


def test_pretrained_loading_is_pinned_by_revision(source: str) -> None:
    assert re.search(r"from_pretrained\([^)]*revision\s*=", source, re.S)


def test_tokenizer_is_bert_tokenizer_fast_saved_for_package(source: str) -> None:
    assert "BertTokenizerFast" in source
    assert "save_pretrained" in source
    assert "tokenizer.json" in source


# --- 匯出與驗證 ---


def test_export_uses_optimum_onnx_and_dynamic_int8_quantization(source: str) -> None:
    assert re.search(r"optimum", source)
    assert re.search(r"onnx", source, re.I)
    assert re.search(r"quantiz", source, re.I)
    assert "model.onnx" in source


def test_logits_compared_pytorch_vs_onnx_with_1e3_tolerance(source: str) -> None:
    assert re.search(r"1e-3|0\.001", source)
    assert re.search(r"abs\(|np\.abs|\.abs\(", source)
    assert re.search(r"\.max\(|max\(", source)
    assert "logits" in source


def test_tokenizer_json_reloaded_with_tokenizers_and_ids_compared(source: str) -> None:
    assert "Tokenizer.from_file" in source
    assert re.search(r"\.ids\b", source)
    assert "input_ids" in source


def test_int8_macro_f1_compared_on_validation_set(source: str) -> None:
    assert re.search(r"f1_score\([^)]*average\s*=\s*[\"']macro[\"']", source, re.S)
    assert re.search(r"int8", source)


def test_validation_is_stratified_10_percent_with_seed(source: str) -> None:
    assert "stratify" in source
    assert re.search(r"test_size\s*=\s*0\.1\b|0\.1", source)


def test_checks_run_before_packaging(source: str) -> None:
    check = source.find("Tokenizer.from_file")
    tol = re.search(r"1e-3|0\.001", source)
    pack = re.search(r"zipfile|make_archive|ZipFile", source)
    assert tol and pack and check >= 0
    assert tol.start() < pack.start()
    assert check < pack.start()
    assert re.search(r"\braise\b|\bassert\b|sys\.exit", source[: pack.start()])


def test_package_contains_the_three_files_and_card_with_sha256(source: str) -> None:
    for name in ("model.onnx", "tokenizer.json", "model_card.json"):
        assert name in source
    assert "sha256" in source
    assert "files" in _string_constants(source)


def test_last_cell_prints_sha256_of_each_package(code_cells: list[str]) -> None:
    last = code_cells[-1]
    assert "sha256" in last.lower()
    assert "print(" in last
    assert ".zip" in last or "zip" in last


# --- 時間預估與續跑 ---


def test_estimates_total_time_after_50_steps_and_stops_over_10_hours(source: str) -> None:
    assert re.search(r"\b50\b", source)
    assert re.search(
        r"36000|10\s*\*\s*3600|10\s*\*\s*60\s*\*\s*60|10\s*hours?|\b10\b.*小時", source
    )
    assert re.search(r"\braise\b|sys\.exit|\bassert\b", source)
    assert "256" in source
    assert "MAX_LEN" in source


def test_checkpoint_saved_each_epoch_and_resumable(source: str) -> None:
    assert re.search(r"save_strategy\s*=\s*[\"']epoch[\"']|save_checkpoint|torch\.save", source)
    assert re.search(r"resume_from_checkpoint|resume", source)
    assert re.search(r"checkpoint", source)

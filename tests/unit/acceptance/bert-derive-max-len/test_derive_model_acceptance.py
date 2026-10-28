"""bert-derive-max-len 驗收測試（開發規格 7.27「修正單」bert-derive-max-len 列）。"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from tests.helpers.onnx_model import (
    CARD_FILE,
    MODEL_FILE,
    TOKENIZER_FILE,
    build_model_dir,
    sha256_file,
)

from radar.common.enums import Polarity
from radar.ml.training.classifier import load_classifier

VERSION = "bert-test-202610210000"
ORIGINAL_MAX_LEN = 64


def _derive(model_dir: Path, max_len: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "radar.ml.training.derive_model",
            "--model",
            str(model_dir),
            "--max-len",
            str(max_len),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def _make(models_dir: Path, version: str = VERSION) -> Path:
    return build_model_dir(models_dir / version, model_version=version, max_len=ORIGINAL_MAX_LEN)


def _card(model_dir: Path) -> dict:
    return json.loads((model_dir / CARD_FILE).read_text())


def _assert_rejected(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode != 0
    assert result.stderr.strip()
    assert "Traceback" not in result.stderr
    assert "No module named" not in result.stderr


def test_derive_creates_len_dir_with_copied_files_and_updated_card(tmp_path: Path) -> None:
    src = _make(tmp_path)
    result = _derive(src, 16)
    assert result.returncode == 0, result.stderr

    target = tmp_path / f"{VERSION}-len16"
    assert target.is_dir()
    for name in (MODEL_FILE, TOKENIZER_FILE):
        assert (target / name).read_bytes() == (src / name).read_bytes()
    card = _card(target)
    assert card["model_version"] == f"{VERSION}-len16"
    assert card["max_len"] == 16
    assert card["params"]["derived_from"] == VERSION
    assert card["files"] == {
        MODEL_FILE: sha256_file(target / MODEL_FILE),
        TOKENIZER_FILE: sha256_file(target / TOKENIZER_FILE),
    }
    assert card["files"] == _card(src)["files"]


def test_derive_leaves_original_untouched(tmp_path: Path) -> None:
    src = _make(tmp_path)
    before = {p.name: p.read_bytes() for p in src.iterdir()}
    assert _derive(src, 16).returncode == 0
    assert {p.name: p.read_bytes() for p in src.iterdir()} == before


def test_derive_keeps_other_card_fields(tmp_path: Path) -> None:
    src = _make(tmp_path)
    assert _derive(src, 16).returncode == 0
    new, old = _card(tmp_path / f"{VERSION}-len16"), _card(src)
    for key in ("labels", "base_model", "kind", "dataset", "max_chars", "created_at"):
        assert new[key] == old[key]


def test_derive_existing_target_is_rejected_and_not_overwritten(tmp_path: Path) -> None:
    src = _make(tmp_path)
    target = tmp_path / f"{VERSION}-len16"
    target.mkdir()
    (target / "marker").write_text("keep")

    _assert_rejected(_derive(src, 16))
    assert [p.name for p in target.iterdir()] == ["marker"]


@pytest.mark.parametrize("max_len", [ORIGINAL_MAX_LEN, ORIGINAL_MAX_LEN + 1, 512])
def test_derive_max_len_not_smaller_is_rejected(tmp_path: Path, max_len: int) -> None:
    src = _make(tmp_path)
    _assert_rejected(_derive(src, max_len))
    assert sorted(p.name for p in tmp_path.iterdir()) == [VERSION]


def test_derive_new_version_over_import_format_is_rejected(tmp_path: Path) -> None:
    # 原版本 62 字元合法；加上 -len16 後超過 import_model 的 64 字元上限
    long_version = "bert-" + "a" * 57
    assert len(long_version) == 62
    src = _make(tmp_path, long_version)
    _assert_rejected(_derive(src, 16))
    assert sorted(p.name for p in tmp_path.iterdir()) == [long_version]


def test_derive_missing_model_dir_is_rejected(tmp_path: Path) -> None:
    _assert_rejected(_derive(tmp_path / "nope", 16))


def test_derived_model_loads_and_truncates_at_new_max_len(tmp_path: Path) -> None:
    src = _make(tmp_path)
    assert _derive(src, 4).returncode == 0
    derived, card = load_classifier(tmp_path / f"{VERSION}-len4", threads=1)
    original, _ = load_classifier(src, threads=1)
    assert card.max_len == 4

    # 4 個 token = [CLS] 今 天 [SEP]；後面的正面詞應被截掉
    long_text = "今天" + "好棒讚漲" * 10
    truncated = derived.predict_proba([long_text])[0]
    prefix_only = derived.predict_proba(["今天"])[0]
    full = original.predict_proba([long_text])[0]
    for label in Polarity:
        assert truncated[label] == pytest.approx(prefix_only[label], abs=1e-9)
    assert full[Polarity.POSITIVE] > truncated[Polarity.POSITIVE] + 0.05

import json
import sys
from pathlib import Path

import pytest

from radar.ml.training import derive_model as mod
from radar.ml.training.derive_model import DeriveError, derive_model, main
from tests.helpers.onnx_model import CARD_FILE, MODEL_FILE, build_model_dir

V = "bert-test-202610210000"


def _src(tmp_path: Path, version: str = V, max_len: int = 64) -> Path:
    return build_model_dir(tmp_path / version, model_version=version, max_len=max_len)


def test_derive_normal_creates_sibling_with_new_card(tmp_path: Path) -> None:
    target = derive_model(_src(tmp_path), 32)
    card = json.loads((target / CARD_FILE).read_text())
    assert target == tmp_path / f"{V}-len32"
    assert card["max_len"] == 32
    assert card["params"]["derived_from"] == V
    assert (target / MODEL_FILE).exists()


def test_derive_leaves_no_staging_dir(tmp_path: Path) -> None:
    derive_model(_src(tmp_path), 32)
    assert sorted(p.name for p in tmp_path.iterdir()) == [V, f"{V}-len32"]


@pytest.mark.parametrize("max_len", [64, 65, 0, -1])
def test_derive_bad_max_len_raises(tmp_path: Path, max_len: int) -> None:
    with pytest.raises(DeriveError):
        derive_model(_src(tmp_path), max_len)


def test_derive_existing_target_raises(tmp_path: Path) -> None:
    (tmp_path / f"{V}-len32").mkdir()
    with pytest.raises(DeriveError, match="already exists"):
        derive_model(_src(tmp_path), 32)


def test_derive_version_too_long_raises(tmp_path: Path) -> None:
    with pytest.raises(DeriveError, match="invalid model_version"):
        derive_model(_src(tmp_path, "bert-" + "a" * 57), 16)


def test_derive_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(DeriveError):
        derive_model(tmp_path / "nope", 16)


def test_derive_invalid_card_raises(tmp_path: Path) -> None:
    src = _src(tmp_path)
    (src / CARD_FILE).write_text("{}")
    with pytest.raises(DeriveError, match="invalid"):
        derive_model(src, 16)


def test_derive_missing_model_file_raises(tmp_path: Path) -> None:
    src = _src(tmp_path)
    (src / MODEL_FILE).unlink()
    with pytest.raises(DeriveError, match="not found"):
        derive_model(src, 16)


def test_derive_card_without_max_len_raises(tmp_path: Path) -> None:
    src = _src(tmp_path)
    card = json.loads((src / CARD_FILE).read_text())
    card["kind"] = "sklearn"
    del card["max_len"]
    (src / CARD_FILE).write_text(json.dumps(card))
    with pytest.raises(DeriveError, match="no max_len"):
        derive_model(src, 16)


def test_derive_copy_failure_cleans_staging_and_reraises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _src(tmp_path)

    def boom(*_a: object, **_k: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mod.shutil, "copyfile", boom)
    with pytest.raises(OSError):
        derive_model(src, 16)
    assert [p.name for p in tmp_path.iterdir()] == [V]


def test_main_success_creates_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    monkeypatch.setattr(sys, "argv", ["derive_model", "--model", str(src), "--max-len", "16"])
    main()
    assert (tmp_path / f"{V}-len16" / CARD_FILE).exists()


def test_main_rejected_exits_nonzero_with_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = _src(tmp_path)
    monkeypatch.setattr(sys, "argv", ["derive_model", "--model", str(src), "--max-len", "64"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert str(exc.value).startswith("error: ")

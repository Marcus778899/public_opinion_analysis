"""bert-model-import 驗收測試（開發規格 7.27「模型包格式」「威脅與對策」）。"""

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.helpers.onnx_model import (
    CARD_FILE,
    MODEL_FILE,
    PACKAGE_FILES,
    TOKENIZER_FILE,
    package_members,
    read_zip,
    sha256_bytes,
    write_zip,
)

from radar.ml.training import import_model as im
from radar.ml.training.import_model import (
    ModelExistsError,
    ModelPackageError,
    import_model,
)
from radar.ml.training.train import ModelCard

MakePackage = Callable[..., Path]


def _leftovers(models_dir: Path) -> list[str]:
    return sorted(p.name for p in models_dir.iterdir()) if models_dir.exists() else []


def _members_with_version(tmp_path: Path, version: str) -> dict[str, bytes]:
    members = package_members(tmp_path / "work")
    card = json.loads(members[CARD_FILE])
    card["model_version"] = version
    members[CARD_FILE] = json.dumps(card).encode()
    return members


def test_valid_package_extracts_three_files_to_version_dir(
    make_model_package: MakePackage, tmp_path: Path
) -> None:
    zip_path = make_model_package()
    expected = read_zip(zip_path)
    models_dir = tmp_path / "models"

    target = import_model(zip_path, models_dir)

    card = ModelCard.model_validate_json(expected[CARD_FILE])
    assert target == models_dir / card.model_version
    assert sorted(p.name for p in target.iterdir()) == sorted(PACKAGE_FILES)
    for name in PACKAGE_FILES:
        assert (target / name).read_bytes() == expected[name]
    assert _leftovers(models_dir) == [card.model_version]


def test_int8_package_imports_under_int8_version(
    make_model_package: MakePackage, tmp_path: Path
) -> None:
    target = import_model(make_model_package(quantized=True), tmp_path / "models")
    assert target.name.endswith("-int8")


@pytest.mark.parametrize("victim", [MODEL_FILE, TOKENIZER_FILE])
def test_hash_mismatch_is_rejected_and_leaves_nothing(
    make_model_package: MakePackage, tmp_path: Path, victim: str
) -> None:
    members = read_zip(make_model_package())
    members[victim] = members[victim] + b"tampered"
    bad = write_zip(tmp_path / "bad.zip", members)
    models_dir = tmp_path / "models"

    with pytest.raises(ModelPackageError):
        import_model(bad, models_dir)

    assert _leftovers(models_dir) == []


def test_card_hash_pointing_to_other_content_is_rejected(tmp_path: Path) -> None:
    members = package_members(tmp_path / "work")
    card = json.loads(members[CARD_FILE])
    card["files"][MODEL_FILE] = sha256_bytes(b"something else")
    members[CARD_FILE] = json.dumps(card).encode()
    bad = write_zip(tmp_path / "bad.zip", members)

    with pytest.raises(ModelPackageError):
        import_model(bad, tmp_path / "models")

    assert _leftovers(tmp_path / "models") == []


def test_extra_member_name_is_rejected(make_model_package: MakePackage, tmp_path: Path) -> None:
    members = read_zip(make_model_package())
    members["extra.txt"] = b"hello"
    bad = write_zip(tmp_path / "bad.zip", members)

    with pytest.raises(ModelPackageError):
        import_model(bad, tmp_path / "models")

    assert _leftovers(tmp_path / "models") == []


def test_missing_member_is_rejected(make_model_package: MakePackage, tmp_path: Path) -> None:
    members = read_zip(make_model_package())
    del members[TOKENIZER_FILE]
    bad = write_zip(tmp_path / "bad.zip", members)

    with pytest.raises(ModelPackageError):
        import_model(bad, tmp_path / "models")

    assert _leftovers(tmp_path / "models") == []


@pytest.mark.parametrize(
    "bad_name",
    [
        f"../{MODEL_FILE}",
        f"../../evil/{MODEL_FILE}",
        f"/abs/{MODEL_FILE}",
        f"sub/{MODEL_FILE}",
    ],
)
def test_path_traversal_member_is_rejected(
    make_model_package: MakePackage, tmp_path: Path, bad_name: str
) -> None:
    members = read_zip(make_model_package())
    members[bad_name] = members.pop(MODEL_FILE)
    bad = write_zip(tmp_path / "bad.zip", members)
    models_dir = tmp_path / "models"

    with pytest.raises(ModelPackageError):
        import_model(bad, models_dir)

    assert _leftovers(models_dir) == []
    assert not (tmp_path / MODEL_FILE).exists()
    assert not (tmp_path / "evil").exists()


def test_total_size_over_limit_is_rejected(
    make_model_package: MakePackage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 不產生真的大檔：把上限調小，內容是高壓縮率的重複位元組
    monkeypatch.setattr(im, "MAX_TOTAL_BYTES", 64 * 1024)
    members = read_zip(make_model_package())
    big = b"\0" * (256 * 1024)
    members[MODEL_FILE] = big
    card = json.loads(members[CARD_FILE])
    card["files"][MODEL_FILE] = sha256_bytes(big)  # 雜湊正確，只有大小違規
    members[CARD_FILE] = json.dumps(card).encode()
    bad = write_zip(tmp_path / "bomb.zip", members)
    assert bad.stat().st_size < 64 * 1024

    with pytest.raises(ModelPackageError):
        import_model(bad, tmp_path / "models")

    assert _leftovers(tmp_path / "models") == []


def test_total_size_within_limit_is_accepted(
    make_model_package: MakePackage, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = make_model_package()
    total = sum(len(v) for v in read_zip(zip_path).values())
    monkeypatch.setattr(im, "MAX_TOTAL_BYTES", total)

    target = import_model(zip_path, tmp_path / "models")

    assert target.is_dir()


def test_size_limit_constant_is_two_gb() -> None:
    assert im.MAX_TOTAL_BYTES == 2 * 1024**3


@pytest.mark.parametrize(
    "version",
    ["../evil", "a/b", "Upper", "-leading", "has space", "", "x" * 65, "a.b", "a\\b"],
)
def test_invalid_model_version_is_rejected(tmp_path: Path, version: str) -> None:
    bad = write_zip(tmp_path / "bad.zip", _members_with_version(tmp_path, version))
    models_dir = tmp_path / "models"

    with pytest.raises(ModelPackageError):
        import_model(bad, models_dir)

    assert _leftovers(models_dir) == []
    assert not (tmp_path / "evil").exists()


def test_model_version_of_64_chars_is_accepted(tmp_path: Path) -> None:
    version = "a" + "b" * 63
    zip_path = write_zip(tmp_path / "ok.zip", _members_with_version(tmp_path, version))

    target = import_model(zip_path, tmp_path / "models")

    assert target.name == version


def test_existing_target_is_rejected_and_untouched(
    make_model_package: MakePackage, tmp_path: Path
) -> None:
    zip_path = make_model_package()
    models_dir = tmp_path / "models"
    target = import_model(zip_path, models_dir)
    marker = target / MODEL_FILE
    before = marker.read_bytes()
    (target / "keep.txt").write_text("mine")

    with pytest.raises(ModelExistsError):
        import_model(zip_path, models_dir)

    assert marker.read_bytes() == before
    assert (target / "keep.txt").read_text() == "mine"
    assert _leftovers(models_dir) == [target.name]


def test_zip_with_card_not_json_is_rejected(
    make_model_package: MakePackage, tmp_path: Path
) -> None:
    members = read_zip(make_model_package())
    members[CARD_FILE] = b"not json"
    bad = write_zip(tmp_path / "bad.zip", members)

    with pytest.raises(ValueError):
        import_model(bad, tmp_path / "models")

    assert _leftovers(tmp_path / "models") == []

import json
from pathlib import Path

import pytest

from radar.ml.training import import_model as im
from radar.ml.training.import_model import ModelPackageError, import_model
from tests.helpers.onnx_model import CARD_FILE, package_members, write_zip


def test_non_zip_file_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(ModelPackageError):
        import_model(bad, tmp_path / "models")


def test_duplicate_member_name_is_rejected(tmp_path: Path) -> None:
    members = package_members(tmp_path / "w")
    zip_path = write_zip(tmp_path / "d.zip", members)
    import zipfile

    with zipfile.ZipFile(zip_path, "a") as zf, pytest.warns(UserWarning):
        zf.writestr(CARD_FILE, b"{}")
    with pytest.raises(ModelPackageError):
        import_model(zip_path, tmp_path / "models")


def test_card_missing_file_hash_entry_is_rejected(tmp_path: Path) -> None:
    members = package_members(tmp_path / "w")
    card = json.loads(members[CARD_FILE])
    del card["files"]["tokenizer.json"]
    members[CARD_FILE] = json.dumps(card).encode()
    with pytest.raises(ModelPackageError):
        import_model(write_zip(tmp_path / "m.zip", members), tmp_path / "models")


def test_card_json_array_is_rejected(tmp_path: Path) -> None:
    members = package_members(tmp_path / "w")
    members[CARD_FILE] = b"[1]"
    with pytest.raises(ModelPackageError):
        import_model(write_zip(tmp_path / "a.zip", members), tmp_path / "models")


def test_card_failing_schema_is_rejected(tmp_path: Path) -> None:
    members = package_members(tmp_path / "w")
    members[CARD_FILE] = json.dumps({"model_version": "ok-1"}).encode()
    with pytest.raises(ModelPackageError):
        import_model(write_zip(tmp_path / "s.zip", members), tmp_path / "models")


def test_failure_while_writing_cleans_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = write_zip(tmp_path / "ok.zip", package_members(tmp_path / "w"))
    monkeypatch.setattr(Path, "rename", lambda *_: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        im.import_model(zip_path, tmp_path / "models")
    assert list((tmp_path / "models").iterdir()) == []

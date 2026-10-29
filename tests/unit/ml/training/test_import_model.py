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


def _zip_path(tmp_path: Path) -> Path:
    return write_zip(tmp_path / "ok.zip", package_members(tmp_path / "w"))


def test_package_sha256_matches_hashlib(tmp_path: Path) -> None:
    import hashlib

    zip_path = _zip_path(tmp_path)
    assert im.package_sha256(zip_path) == hashlib.sha256(zip_path.read_bytes()).hexdigest()


def test_sha256_uppercase_matches_and_imports(tmp_path: Path) -> None:
    zip_path = _zip_path(tmp_path)
    target = import_model(zip_path, tmp_path / "models", sha256=im.package_sha256(zip_path).upper())
    assert target.is_dir()


def test_sha256_mismatch_raises_and_writes_nothing(tmp_path: Path) -> None:
    zip_path = _zip_path(tmp_path)
    with pytest.raises(ModelPackageError, match=im.package_sha256(zip_path)):
        import_model(zip_path, tmp_path / "models", sha256="0" * 64)
    assert not (tmp_path / "models").exists()


def test_kind_sklearn_is_rejected(tmp_path: Path) -> None:
    members = package_members(tmp_path / "w")
    card = json.loads(members[CARD_FILE])
    card["kind"] = "sklearn"
    members[CARD_FILE] = json.dumps(card).encode()
    with pytest.raises(ModelPackageError):
        import_model(write_zip(tmp_path / "k.zip", members), tmp_path / "models")


def test_encrypted_flag_is_rejected_before_reading(tmp_path: Path) -> None:
    import zipfile

    zip_path = _zip_path(tmp_path)
    data = bytearray(zip_path.read_bytes())
    # 把中央目錄每筆的 general purpose flag（偏移 8）設加密位元
    pos = data.find(b"PK\x01\x02")
    while pos != -1:
        data[pos + 8] |= 0x1
        pos = data.find(b"PK\x01\x02", pos + 4)
    zip_path.write_bytes(bytes(data))
    assert all(i.flag_bits & 1 for i in zipfile.ZipFile(zip_path).infolist())
    with pytest.raises(ModelPackageError, match="encrypted"):
        import_model(zip_path, tmp_path / "models")


def test_bzip2_compression_is_rejected(tmp_path: Path) -> None:
    import zipfile

    members = package_members(tmp_path / "w")
    bad = tmp_path / "b.zip"
    with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_BZIP2) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    with pytest.raises(ModelPackageError, match="compression"):
        import_model(bad, tmp_path / "models")


def _run_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *args: str) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["import_model", *args])
    im.main()


def test_main_missing_zip_exits_with_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, tmp_path, "--zip", str(tmp_path / "nope.zip"))
    assert "nope.zip" in str(exc.value.code)


def test_main_existing_version_exits_with_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    zip_path = _zip_path(tmp_path)
    _run_main(monkeypatch, tmp_path, "--zip", str(zip_path))
    with pytest.raises(SystemExit) as exc:
        _run_main(monkeypatch, tmp_path, "--zip", str(zip_path))
    assert "already exists" in str(exc.value.code)

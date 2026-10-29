"""驗收 import-model-hardening（#173/#174/#177/#162）：import_model 的指令列與模型包檢查。

指令列在子行程跑 `python -m`，才看得到結束碼與輸出；MODELS_DIR 是相對路徑，所以 cwd 設為 tmp_path。
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import zipfile
from collections.abc import Callable
from pathlib import Path

import pytest
from tests.helpers.onnx_model import CARD_FILE, read_zip, write_zip

from radar.ml.training.import_model import ModelPackageError, import_model

MODULE = "radar.ml.training.import_model"
MakePackage = Callable[..., Path]


def run_cli(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("COLUMNS")}
    env["COLUMNS"] = "200"
    return subprocess.run(
        [sys.executable, "-m", MODULE, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=120,
        check=False,
    )


def output_of(proc: subprocess.CompletedProcess[str]) -> str:
    return proc.stdout + proc.stderr


def assert_clean_failure(proc: subprocess.CompletedProcess[str]) -> str:
    out = output_of(proc)
    assert proc.returncode != 0, f"expected non-zero exit\n{out}"
    assert "Traceback" not in out, out
    return out


def zip_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------- #173 錯誤提示 ----------


def test_cli_missing_zip_exits_nonzero_with_hint_and_no_traceback(tmp_path):
    missing = tmp_path / "nope.zip"
    out = assert_clean_failure(run_cli(["--zip", str(missing)], tmp_path))
    assert "nope.zip" in out


def test_cli_not_a_zip_exits_nonzero_with_hint_and_no_traceback(tmp_path):
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"this is not a zip")
    out = assert_clean_failure(run_cli(["--zip", str(bogus)], tmp_path))
    assert "zip" in out.lower()


def test_cli_existing_version_exits_nonzero_with_hint_and_no_traceback(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    first = run_cli(["--zip", str(zip_path)], tmp_path)
    assert first.returncode == 0, output_of(first)
    out = assert_clean_failure(run_cli(["--zip", str(zip_path)], tmp_path))
    version = zip_path.stem
    assert version in out


def test_cli_tampered_package_exits_nonzero_without_traceback(
    make_model_package: MakePackage, tmp_path
):
    members = read_zip(make_model_package())
    members["model.onnx"] += b"x"
    bad = write_zip(tmp_path / "bad.zip", members)
    assert_clean_failure(run_cli(["--zip", str(bad)], tmp_path))


def test_cli_failure_message_is_short(tmp_path):
    out = output_of(run_cli(["--zip", str(tmp_path / "nope.zip")], tmp_path))
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert len(lines) <= 3, lines


# ---------- #174 --help ----------


def test_help_describes_every_argument(tmp_path):
    proc = run_cli(["--help"], tmp_path)
    assert proc.returncode == 0, output_of(proc)
    text = re.sub(r"\s+", " ", proc.stdout)
    for flag in ("--zip", "--sha256"):
        match = re.search(rf"{flag}\b[^\n]*", proc.stdout)
        assert match, f"{flag} missing from --help\n{proc.stdout}"
    # 每個參數的說明：參數列後面（同行或下一行縮排）要有文字
    for flag in ("--zip", "--sha256"):
        block = re.search(
            rf"^\s+{flag}\b.*?(?=^\s+-|\Z)", proc.stdout, flags=re.MULTILINE | re.DOTALL
        )
        assert block, flag
        body = re.sub(rf"{flag}\s+\S+", "", block.group(0), count=1)
        assert len(body.split()) >= 2, f"{flag} has no description\n{text}"


# ---------- #177 --sha256 ----------


def test_cli_prints_package_sha256_without_option(make_model_package: MakePackage, tmp_path):
    zip_path = make_model_package()
    proc = run_cli(["--zip", str(zip_path)], tmp_path)
    assert proc.returncode == 0, output_of(proc)
    assert zip_sha256(zip_path) in output_of(proc)


def test_cli_matching_sha256_imports(make_model_package: MakePackage, tmp_path):
    zip_path = make_model_package()
    digest = zip_sha256(zip_path)
    proc = run_cli(["--zip", str(zip_path), "--sha256", digest], tmp_path)
    assert proc.returncode == 0, output_of(proc)
    assert (tmp_path / "models" / zip_path.stem / "model.onnx").exists()
    assert digest in output_of(proc)


def test_cli_sha256_comparison_ignores_case(make_model_package: MakePackage, tmp_path):
    zip_path = make_model_package()
    proc = run_cli(["--zip", str(zip_path), "--sha256", zip_sha256(zip_path).upper()], tmp_path)
    assert proc.returncode == 0, output_of(proc)


def test_cli_mismatching_sha256_rejects_and_imports_nothing(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    wrong = "0" * 64
    out = assert_clean_failure(run_cli(["--zip", str(zip_path), "--sha256", wrong], tmp_path))
    assert zip_sha256(zip_path) in out
    models = tmp_path / "models"
    assert not models.exists() or list(models.iterdir()) == []


def test_function_accepts_expected_sha256_keyword(make_model_package: MakePackage, tmp_path):
    zip_path = make_model_package()
    target = import_model(zip_path, tmp_path / "models", sha256=zip_sha256(zip_path))
    assert target.name == zip_path.stem


def test_function_mismatching_sha256_raises_package_error_and_leaves_nothing(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    models = tmp_path / "models"
    with pytest.raises(ModelPackageError):
        import_model(zip_path, models, sha256="f" * 64)
    assert not models.exists() or list(models.iterdir()) == []


# ---------- #162 kind、加密、壓縮法 ----------


def test_card_kind_not_onnx_is_rejected(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    card = json.loads(members[CARD_FILE])
    card["kind"] = "sklearn"
    members[CARD_FILE] = json.dumps(card).encode()
    bad = write_zip(tmp_path / "sk.zip", members)
    models = tmp_path / "models"
    with pytest.raises(ModelPackageError):
        import_model(bad, models)
    assert not models.exists() or list(models.iterdir()) == []


def test_encrypted_member_raises_package_error(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    bad = tmp_path / "enc.zip"
    with zipfile.ZipFile(bad, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            info = zipfile.ZipInfo(name)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.flag_bits |= 0x1
            zf.writestr(info, data)
    models = tmp_path / "models"
    with pytest.raises(ModelPackageError):
        import_model(bad, models)
    assert not models.exists() or list(models.iterdir()) == []


@pytest.mark.parametrize("method", [zipfile.ZIP_BZIP2, zipfile.ZIP_LZMA])
def test_unsupported_compression_raises_package_error(
    make_model_package: MakePackage, tmp_path, method
):
    members = read_zip(make_model_package())
    bad = tmp_path / "comp.zip"
    with zipfile.ZipFile(bad, "w", compression=method) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    models = tmp_path / "models"
    with pytest.raises(ModelPackageError):
        import_model(bad, models)
    assert not models.exists() or list(models.iterdir()) == []


@pytest.mark.parametrize("method", [zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED])
def test_stored_and_deflated_packages_still_import(
    make_model_package: MakePackage, tmp_path, method
):
    members = read_zip(make_model_package())
    ok = tmp_path / "ok.zip"
    with zipfile.ZipFile(ok, "w", compression=method) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    target = import_model(ok, tmp_path / "models")
    assert (target / "model.onnx").exists()

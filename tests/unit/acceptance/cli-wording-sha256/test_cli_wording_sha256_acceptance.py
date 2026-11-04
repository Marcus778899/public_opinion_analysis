"""驗收 cli-wording-sha256（#263、#270、#271）：import_model 文案、--sha256 必填、derive --help。"""

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from tests.helpers.onnx_model import read_zip, write_zip

MakePackage = Callable[..., Path]
CJK = re.compile(r"[一-鿿]")


def run_module(module: str, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("COLUMNS")}
    env["COLUMNS"] = "200"
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        timeout=120,
        check=False,
    )


def run_import(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return run_module("radar.ml.training.import_model", args, cwd)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def assert_one_line_error(
    proc: subprocess.CompletedProcess[str], zip_path: Path | None = None
) -> str:
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "Traceback" not in out, out
    errors = [ln for ln in out.splitlines() if ln.startswith("error:")]
    assert len(errors) == 1, out
    assert CJK.search(errors[0]), errors[0]
    # error 行之外：檔案不存在時不可有其他行；否則最多一行，且必須是整包 SHA-256
    others = [ln for ln in out.splitlines() if ln.strip() and not ln.startswith("error:")]
    if zip_path is None:
        assert not others, out
    else:
        assert len(others) <= 1, out
        assert all(sha(zip_path) in ln for ln in others), out
    return errors[0]


def test_missing_zip_prints_one_chinese_line_with_path_once(tmp_path):
    missing = tmp_path / "nope.zip"
    line = assert_one_line_error(
        run_import(["--zip", str(missing), "--sha256", "0" * 64], tmp_path)
    )
    assert line.count("nope.zip") == 1
    assert "Errno" not in line


def test_not_a_zip_prints_one_chinese_line(tmp_path):
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"not a zip")
    line = assert_one_line_error(
        run_import(["--zip", str(bogus), "--sha256", sha(bogus)], tmp_path), bogus
    )
    assert "zip" in line.lower()


def test_existing_version_says_no_overwrite_and_next_step(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    args = ["--zip", str(zip_path), "--sha256", sha(zip_path)]
    assert run_import(args, tmp_path).returncode == 0
    line = assert_one_line_error(run_import(args, tmp_path), zip_path)
    assert zip_path.stem in line
    assert "不會覆寫" in line
    assert "models/" in line


def test_sha256_mismatch_prints_actual_and_says_redownload(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    line = assert_one_line_error(
        run_import(["--zip", str(zip_path), "--sha256", "0" * 64], tmp_path), zip_path
    )
    assert sha(zip_path) in line
    assert "重新下載" in line


def test_validation_failure_prints_one_chinese_line(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    members["model.onnx"] += b"x"
    bad = write_zip(tmp_path / "bad.zip", members)
    assert_one_line_error(run_import(["--zip", str(bad), "--sha256", sha(bad)], tmp_path), bad)


def test_missing_sha256_option_exits_2_and_names_option(make_model_package: MakePackage, tmp_path):
    zip_path = make_model_package()
    proc = run_import(["--zip", str(zip_path)], tmp_path)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "--sha256" in proc.stderr
    assert not (tmp_path / "models").exists()


def test_help_describes_sha256_as_notebook_last_cell(tmp_path):
    proc = run_import(["--help"], tmp_path)
    assert proc.returncode == 0
    text = re.sub(r"\s+", " ", proc.stdout)
    assert "notebook" in text and "sha256" in text.lower()


def test_derive_model_help_describes_both_arguments(tmp_path):
    proc = run_module("radar.ml.training.derive_model", ["--help"], tmp_path)
    assert proc.returncode == 0, proc.stderr
    for flag in ("--model", "--max-len"):
        block = re.search(
            rf"^\s+{flag}\b.*?(?=^\s+-|^\S|\Z)", proc.stdout, flags=re.MULTILINE | re.DOTALL
        )
        assert block, f"{flag} missing\n{proc.stdout}"
        body = re.sub(rf"{flag}\s+\S+", "", block.group(0), count=1)
        assert len(body.split()) >= 2, f"{flag} has no description\n{proc.stdout}"
    assert "len" in proc.stdout  # 說明產生 models/<版本>-len<N>/


# 回歸（qa FAIL 1）：ModelPackageError 的原因也要中文，不可原樣露出英文句子
REASON = re.compile(r"（(?P<reason>[^（）]*)）")
TECH_TOKEN = re.compile(r"\S*[._\d]\S*|zip|onnx|json|utf|sha|\W+", re.IGNORECASE)


def assert_reason_is_chinese(line: str) -> None:
    match = REASON.search(line)
    assert match, f"no （原因） in: {line}"
    reason = match.group("reason")
    assert CJK.search(reason), reason
    # 去掉檔名、雜湊、zip／onnx／json 等技術名詞後，不可再有英文單字
    leftover = re.findall(r"[A-Za-z]{3,}", TECH_TOKEN.sub(" ", reason))
    assert not leftover, f"English words {leftover} in: {line}"


def _fail_line(zip_path: Path, cwd: Path) -> str:
    return assert_one_line_error(
        run_import(["--zip", str(zip_path), "--sha256", sha(zip_path)], cwd), zip_path
    )


def test_not_a_zip_reason_is_chinese(tmp_path):
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"not a zip")
    assert_reason_is_chinese(_fail_line(bogus, tmp_path))


def test_unexpected_members_reason_is_chinese(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    members["extra.txt"] = b"x"
    assert_reason_is_chinese(_fail_line(write_zip(tmp_path / "x.zip", members), tmp_path))


def test_member_sha256_mismatch_reason_is_chinese(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    members["model.onnx"] += b"x"
    assert_reason_is_chinese(_fail_line(write_zip(tmp_path / "x.zip", members), tmp_path))


def test_card_not_json_reason_is_chinese(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    members["model_card.json"] = b"not json"
    assert_reason_is_chinese(_fail_line(write_zip(tmp_path / "x.zip", members), tmp_path))


def test_invalid_model_version_reason_is_chinese(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    card = json.loads(members["model_card.json"])
    card["model_version"] = "../Bad Version"
    members["model_card.json"] = json.dumps(card).encode()
    assert_reason_is_chinese(_fail_line(write_zip(tmp_path / "x.zip", members), tmp_path))


def test_invalid_card_reason_is_chinese(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    card = json.loads(members["model_card.json"])
    card.pop("files", None)
    members["model_card.json"] = json.dumps(card).encode()
    assert_reason_is_chinese(_fail_line(write_zip(tmp_path / "x.zip", members), tmp_path))


def test_card_kind_not_onnx_reason_is_chinese(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    card = json.loads(members["model_card.json"])
    card["kind"] = "sklearn"
    members["model_card.json"] = json.dumps(card).encode()
    assert_reason_is_chinese(_fail_line(write_zip(tmp_path / "x.zip", members), tmp_path))


# C1：失敗路徑的輸出（stdout+stderr）都要含整包 SHA-256
def _output(zip_path: Path, cwd: Path, given: str | None = None) -> str:
    proc = run_import(["--zip", str(zip_path), "--sha256", given or sha(zip_path)], cwd)
    return proc.stdout + proc.stderr


def test_not_a_zip_output_contains_package_sha256(tmp_path):
    bogus = tmp_path / "bogus.zip"
    bogus.write_bytes(b"not a zip")
    assert sha(bogus) in _output(bogus, tmp_path)


def test_existing_version_output_contains_package_sha256(make_model_package: MakePackage, tmp_path):
    zip_path = make_model_package()
    assert run_import(["--zip", str(zip_path), "--sha256", sha(zip_path)], tmp_path).returncode == 0
    assert sha(zip_path) in _output(zip_path, tmp_path)


def test_validation_failure_output_contains_package_sha256(
    make_model_package: MakePackage, tmp_path
):
    members = read_zip(make_model_package())
    members["model.onnx"] += b"x"
    bad = write_zip(tmp_path / "bad.zip", members)
    assert sha(bad) in _output(bad, tmp_path)


def test_package_sha256_mismatch_output_contains_actual_sha256(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    assert sha(zip_path) in _output(zip_path, tmp_path, given="0" * 64)

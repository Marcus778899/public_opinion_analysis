"""驗收 cli-wording-sha256（#263、#270、#271）：import_model 文案、--sha256 必填、derive --help。"""

import hashlib
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


def assert_one_line_error(proc: subprocess.CompletedProcess[str]) -> str:
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "Traceback" not in out, out
    errors = [ln for ln in out.splitlines() if ln.startswith("error:")]
    assert len(errors) == 1, out
    assert CJK.search(errors[0]), errors[0]
    # 一行：error 行之外不可再有其他非空行
    assert len([ln for ln in out.splitlines() if ln.strip()]) == 1, out
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
        run_import(["--zip", str(bogus), "--sha256", sha(bogus)], tmp_path)
    )
    assert "zip" in line.lower()


def test_existing_version_says_no_overwrite_and_next_step(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    args = ["--zip", str(zip_path), "--sha256", sha(zip_path)]
    assert run_import(args, tmp_path).returncode == 0
    line = assert_one_line_error(run_import(args, tmp_path))
    assert zip_path.stem in line
    assert "不會覆寫" in line
    assert "models/" in line


def test_sha256_mismatch_prints_actual_and_says_redownload(
    make_model_package: MakePackage, tmp_path
):
    zip_path = make_model_package()
    line = assert_one_line_error(
        run_import(["--zip", str(zip_path), "--sha256", "0" * 64], tmp_path)
    )
    assert sha(zip_path) in line
    assert "重新下載" in line


def test_validation_failure_prints_one_chinese_line(make_model_package: MakePackage, tmp_path):
    members = read_zip(make_model_package())
    members["model.onnx"] += b"x"
    bad = write_zip(tmp_path / "bad.zip", members)
    assert_one_line_error(run_import(["--zip", str(bad), "--sha256", sha(bad)], tmp_path))


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

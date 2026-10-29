"""驗收 ml-cli-usability（#173/#174/#175/#176/#168）：evaluate、compare、cross_check 的指令列行為。

指令列行為在子行程跑 `python -m`，才看得到真正的結束碼與輸出；一律不連真實服務。
"""

import csv
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from radar.common.enums import Polarity
from radar.ml.labeling.cross_check import Disagreement, write_disagreements_csv
from radar.ml.labeling.prompt import PostText
from radar.ml.training import compare

EVALUATE = "radar.ml.training.evaluate"
COMPARE = "radar.ml.training.compare"
CROSS_CHECK = "radar.ml.labeling.cross_check"

# 連不到的位址：萬一沒被提早擋下，也只會是連線錯誤而不是通過
CH_ENV = {
    "CLICKHOUSE_URL": "http://127.0.0.1:1",
    "CLICKHOUSE_USER": "u",
    "CLICKHOUSE_PASSWORD": "p",
}
ENV_HINT = "uv run --env-file .env"


def run_module(
    module: str, args: list[str], tmp_path: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    full_env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CLICKHOUSE_", "INFERENCE_", "LABEL_", "GEMINI_", "GROQ_"))
    }
    full_env["COLUMNS"] = "200"
    full_env.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True,
        text=True,
        env=full_env,
        cwd=tmp_path,
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


# ---------- #173 evaluate：模型資料夾 ----------


def test_evaluate_missing_model_dir_exits_nonzero_with_one_line_hint(tmp_path):
    missing = tmp_path / "models" / "nope"
    proc = run_module(EVALUATE, ["--model", str(missing)], tmp_path, CH_ENV)
    out = assert_clean_failure(proc)
    assert str(missing) in out or "nope" in out


def test_evaluate_dir_without_model_card_exits_nonzero_without_traceback(tmp_path):
    empty = tmp_path / "models" / "empty"
    empty.mkdir(parents=True)
    proc = run_module(EVALUATE, ["--model", str(empty)], tmp_path, CH_ENV)
    out = assert_clean_failure(proc)
    assert "empty" in out


def test_evaluate_missing_model_dir_message_is_a_single_error_line(tmp_path):
    missing = tmp_path / "models" / "nope"
    proc = run_module(EVALUATE, ["--model", str(missing)], tmp_path, CH_ENV)
    lines = [ln for ln in output_of(proc).splitlines() if ln.strip()]
    assert len(lines) <= 3, lines


# ---------- #175 缺 ClickHouse 環境變數 ----------


def test_evaluate_missing_clickhouse_env_names_variables_and_hint(tmp_path, tiny_model_dir):
    proc = run_module(EVALUATE, ["--model", str(tiny_model_dir)], tmp_path)
    out = assert_clean_failure(proc)
    assert "CLICKHOUSE_USER" in out
    assert "CLICKHOUSE_PASSWORD" in out
    assert ENV_HINT in out


def test_compare_missing_clickhouse_env_names_variables_and_hint(tmp_path):
    args = ["--a", "m-a", "--b", "m-b", "--since", "2026-10-27T00:00:00+00:00"]
    proc = run_module(COMPARE, args, tmp_path)
    out = assert_clean_failure(proc)
    assert "CLICKHOUSE_USER" in out
    assert "CLICKHOUSE_PASSWORD" in out
    assert ENV_HINT in out


def test_cross_check_missing_clickhouse_env_names_variables_and_hint(tmp_path):
    args = ["--primary", "some-labeler", "--out", str(tmp_path / "d.csv")]
    proc = run_module(CROSS_CHECK, args, tmp_path)
    out = assert_clean_failure(proc)
    assert "CLICKHOUSE_USER" in out
    assert "CLICKHOUSE_PASSWORD" in out
    assert ENV_HINT in out


def test_cross_check_only_password_missing_names_only_password(tmp_path):
    args = ["--primary", "some-labeler", "--out", str(tmp_path / "d.csv")]
    proc = run_module(CROSS_CHECK, args, tmp_path, {"CLICKHOUSE_USER": "u"})
    out = assert_clean_failure(proc)
    assert "CLICKHOUSE_PASSWORD" in out
    assert "CLICKHOUSE_USER" not in out


# ---------- #174 --help ----------


def option_blocks(help_text: str) -> dict[str, str]:
    """回傳 {選項名稱: 說明文字}；說明可在選項同一行（2 個以上空白後）或下一行起。"""
    blocks: dict[str, list[str]] = {}
    current = None
    for line in help_text.splitlines():
        m = re.match(r"^\s{2}(-\S+)(.*)$", line)
        if m:
            name = [t for t in re.findall(r"--[\w-]+", line)] or [m.group(1)]
            current = name[0]
            rest = re.split(r"\s{2,}", m.group(2).strip(), maxsplit=1)
            blocks[current] = [rest[1]] if len(rest) == 2 else []
        elif current and line.startswith("   ") and line.strip():
            blocks[current].append(line.strip())
        elif not line.strip():
            current = None
    return {k: " ".join(v) for k, v in blocks.items()}


@pytest.mark.parametrize(
    ("module", "options"),
    [(EVALUATE, {"--model"}), (COMPARE, {"--a", "--b", "--since"})],
)
def test_help_every_option_has_description(module, options, tmp_path):
    proc = run_module(module, ["--help"], tmp_path)
    assert proc.returncode == 0, output_of(proc)
    blocks = option_blocks(proc.stdout)
    assert options <= blocks.keys(), blocks
    for name in options:
        assert blocks[name].strip(), f"{name} has no help text:\n{proc.stdout}"


def test_compare_help_since_has_iso_example_and_timezone_note(tmp_path):
    proc = run_module(COMPARE, ["--help"], tmp_path)
    text = option_blocks(proc.stdout)["--since"]
    assert re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", text), text
    assert "UTC" in text, text


# ---------- #176 CSV 公式注入 ----------

DANGEROUS = ["=1+1", "+cmd", "-cmd", "@SUM(A1)", "\t=x", "\r=x"]
SAFE = ["普通標題", "a=b", "x+y", "", "[新聞] 標題", " =leading space"]


def paired(title: str, board: str = "Gossiping", pid: str = "Gossiping.M.1.A.001"):
    return compare.PairedPrediction(
        post_id=pid,
        board=board,
        title=title,
        polarity_a=Polarity.POSITIVE,
        score_a=0.9,
        polarity_b=Polarity.NEGATIVE,
        score_b=0.8,
        llm=None,
    )


def compare_titles(tmp_path: Path, titles: list[str]) -> list[str]:
    pairs = [paired(t, pid=f"Gossiping.M.{i}.A.001") for i, t in enumerate(titles)]
    path = tmp_path / "d.csv"
    assert compare.write_disagreements(path, pairs) == len(titles)
    with path.open(encoding="utf-8", newline="") as f:
        by_id = {r["post_id"]: r["title"] for r in csv.DictReader(f)}
    return [by_id[f"Gossiping.M.{i}.A.001"] for i in range(len(titles))]


def cross_check_titles(tmp_path: Path, titles: list[str]) -> list[str]:
    rows = [
        Disagreement(f"Gossiping.M.{i}.A.001", Polarity.POSITIVE, Polarity.NEGATIVE)
        for i in range(len(titles))
    ]
    posts = {
        r.post_id: PostText(r.post_id, "Gossiping", t, None)
        for r, t in zip(rows, titles, strict=True)
    }
    path = tmp_path / "d.csv"
    write_disagreements_csv(rows, posts, path)
    with path.open(encoding="utf-8-sig", newline="") as f:
        by_id = {r["post_id"]: r["title"] for r in csv.DictReader(f)}
    return [by_id[r.post_id] for r in rows]


@pytest.mark.parametrize("writer", [compare_titles, cross_check_titles])
def test_csv_dangerous_prefix_gets_leading_apostrophe(writer, tmp_path):
    assert writer(tmp_path, DANGEROUS) == ["'" + t for t in DANGEROUS]


@pytest.mark.parametrize("writer", [compare_titles, cross_check_titles])
def test_csv_safe_values_unchanged(writer, tmp_path):
    assert writer(tmp_path, SAFE) == SAFE


def test_compare_csv_board_field_is_also_neutralised(tmp_path):
    path = tmp_path / "d.csv"
    compare.write_disagreements(path, [paired("t", board="=evil")])
    with path.open(encoding="utf-8", newline="") as f:
        assert next(csv.DictReader(f))["board"] == "'=evil"


def test_compare_csv_numeric_and_polarity_columns_unchanged(tmp_path):
    path = tmp_path / "d.csv"
    compare.write_disagreements(path, [paired("=x")])
    with path.open(encoding="utf-8", newline="") as f:
        row = next(csv.DictReader(f))
    assert (row["polarity_a"], row["score_a"], row["polarity_b"], row["score_b"]) == (
        "positive",
        "0.900",
        "negative",
        "0.800",
    )


# ---------- #168 compare ----------


@pytest.mark.parametrize("flag", ["--a", "--b"])
@pytest.mark.parametrize("bad", ["Bad Version", "../x", "UPPER", "a;drop", "-lead", ""])
def test_compare_malformed_version_rejected_before_connecting(flag, bad, tmp_path):
    args = {"--a": "bert-a-1", "--b": "bert-b-1", "--since": "2026-10-27T00:00:00+00:00"}
    args[flag] = bad
    argv = [x for k, v in args.items() for x in (k, v)]
    proc = run_module(COMPARE, argv, tmp_path, CH_ENV)
    out = assert_clean_failure(proc)
    assert flag in out or flag[2:] in out


class RecordingClient:
    def __init__(self) -> None:
        self.sql: list[str] = []

    def query_rows(self, sql, params=None):
        self.sql.append(sql)
        return []


def test_fetch_pairs_polarity_and_score_not_picked_by_independent_argmax():
    # NOTE: 單元層無法執行 ClickHouse SQL，只能檢查文字：同一 predicted_at 有多筆時，
    # 兩個獨立的 argMax 可能挑到不同列；改用 tuple 的 argMax 或 LIMIT 1 BY 皆可
    client = RecordingClient()
    since = datetime(2026, 10, 27, tzinfo=UTC)
    compare.fetch_pairs(client, "bert-a-1", "bert-b-1", since, "labeler", "v1")
    sql = client.sql[0]
    independent = re.search(r"argMax\(\s*polarity\s*,\s*predicted_at\s*\)", sql) and re.search(
        r"argMax\(\s*arrayMax\(mapValues\(scores\)\)\s*,\s*predicted_at\s*\)", sql
    )
    assert not independent, sql
    assert "predicted_at" in sql

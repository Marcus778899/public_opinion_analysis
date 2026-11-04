"""驗收 replay-alert-repro（#261，UAT v0.8.1 F-1、F-2）。

只測 CLI 對外行為（--help、錯誤輸出與結束碼）與開發規格 7.20 的文字；
不連 Kafka、Apicurio，不假設實作內部的函式名稱。「replay.alerts 真的收到警示」由 QA 實跑驗。
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from radar.streaming import replay as replay_mod

ROOT = Path(__file__).resolve().parents[4]
SPEC = ROOT / "docs" / "development-spec.md"
VALID_POST = "Stock.M.1792000000.A.ABC"

EXPECTED_OPTIONS = {
    "record": {"--since", "--until", "--out"},
    "replay": {"--file", "--speed"},
    "surge": {"--post-id", "--count", "--minutes", "--start-floor"},
}


@pytest.fixture(autouse=True)
def _no_external(monkeypatch: pytest.MonkeyPatch) -> None:
    """In-process 測試不連任何外部服務，也不改 log 設定。"""
    monkeypatch.setattr(replay_mod, "setup_logging", lambda *_a, **_k: None)
    for name in ("Consumer", "Producer", "SchemaRegistryClient"):
        monkeypatch.setattr(replay_mod, name, MagicMock())
    for name in ("get_kafka_settings", "consumer_config", "producer_config"):
        monkeypatch.setattr(replay_mod, name, MagicMock())


def _run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *argv: str
) -> tuple[int | str | None, str]:
    monkeypatch.setattr(sys, "argv", ["replay", *argv])
    code: int | str | None = None
    try:
        replay_mod.main()
    except SystemExit as e:
        code = e.code
    captured = capsys.readouterr()
    text = captured.out + captured.err
    if isinstance(code, str):
        text += code + "\n"
    return code, text


def _is_failure(code: int | str | None) -> bool:
    return code is not None and code != 0


def _message_lines(text: str) -> list[str]:
    """去掉 argparse 的 usage 區塊後剩下的說明行。"""
    lines = []
    in_usage = False
    for line in text.splitlines():
        if not line.strip():
            in_usage = False
            continue
        if line.startswith("usage:"):
            in_usage = True
            continue
        if in_usage and line.startswith((" ", "\t")):
            continue
        in_usage = False
        lines.append(line)
    return lines


def _assert_one_line_error(code: int | str | None, text: str) -> None:
    assert _is_failure(code), f"expected non-zero exit, got {code!r}; output={text!r}"
    assert "Traceback" not in text
    assert len(_message_lines(text)) == 1, f"expected one-line message, got: {text!r}"


# --- --help ---


def _option_blocks(help_text: str) -> dict[str, str]:
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in help_text.splitlines():
        m = re.match(r"^\s{1,4}(-\S+)", line)
        if m:
            current = m.group(1).rstrip(",")
            blocks[current] = [line]
        elif current and line.startswith("   ") and line.strip():
            blocks[current].append(line)
        else:
            current = None
    return {k: "\n".join(v) for k, v in blocks.items()}


def _has_description(block: str) -> bool:
    lines = block.splitlines()
    if len(lines) > 1:
        return True
    return re.search(r"\S\s{2,}\S", lines[0].strip()) is not None


@pytest.mark.parametrize("command", sorted(EXPECTED_OPTIONS))
def test_subcommand_help_every_option_has_description(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, text = _run(monkeypatch, capsys, command, "--help")
    assert code == 0
    blocks = _option_blocks(text)
    missing = EXPECTED_OPTIONS[command] - set(blocks)
    assert not missing, f"options not in --help: {missing}\n{text}"
    undocumented = [
        o for o, b in blocks.items() if o not in ("-h", "--help") and not _has_description(b)
    ]
    assert not undocumented, f"options without help text: {undocumented}\n{text}"


def test_top_level_help_describes_each_subcommand(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, text = _run(monkeypatch, capsys, "--help")
    assert code == 0
    for command in EXPECTED_OPTIONS:
        assert re.search(rf"^\s+{command}\s{{2,}}\S", text, re.M), f"{command} lacks description"


# --- 常見輸入錯誤：一行說明、非 0、不印 traceback ---


def test_replay_missing_file_prints_one_line_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, text = _run(monkeypatch, capsys, "replay", "--file", str(tmp_path / "nope.jsonl"))
    _assert_one_line_error(code, text)
    assert "nope.jsonl" in text


def test_replay_file_with_bad_line_prints_one_line_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bad = tmp_path / "bad.jsonl"
    bad.write_text("this is not json\n")
    code, text = _run(monkeypatch, capsys, "replay", "--file", str(bad))
    _assert_one_line_error(code, text)


@pytest.mark.parametrize("speed", ["-1", "0", "abc"])
def test_replay_invalid_speed_prints_one_line_and_fails(
    speed: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    f = tmp_path / "x.jsonl"
    f.write_text("")
    code, text = _run(monkeypatch, capsys, "replay", "--file", str(f), f"--speed={speed}")
    _assert_one_line_error(code, text)


@pytest.mark.parametrize("since", ["yesterday", "2026-13-45", "10/30"])
def test_record_invalid_since_prints_one_line_and_fails(
    since: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, text = _run(
        monkeypatch,
        capsys,
        "record",
        "--since",
        since,
        "--until",
        "2026-10-30T00:00:00+00:00",
        "--out",
        str(tmp_path / "o.jsonl"),
    )
    _assert_one_line_error(code, text)


def test_record_since_after_until_prints_one_line_and_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, text = _run(
        monkeypatch,
        capsys,
        "record",
        "--since",
        "2026-10-30T10:00:00+00:00",
        "--until",
        "2026-10-30T09:00:00+00:00",
        "--out",
        str(tmp_path / "o.jsonl"),
    )
    _assert_one_line_error(code, text)


@pytest.mark.parametrize(
    "extra",
    [
        ["--post-id", "not-a-post-id"],
        ["--post-id", VALID_POST, "--count", "0"],
        ["--post-id", VALID_POST, "--count", "-5"],
        ["--post-id", VALID_POST, "--minutes", "0"],
        ["--post-id", VALID_POST, "--minutes", "-3"],
    ],
)
def test_surge_invalid_input_prints_one_line_and_fails(
    extra: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, text = _run(monkeypatch, capsys, "surge", *extra)
    _assert_one_line_error(code, text)


def test_missing_required_option_fails_without_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, text = _run(monkeypatch, capsys, "replay")
    assert _is_failure(code)
    assert "Traceback" not in text


def test_input_errors_do_not_reach_kafka(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _run(monkeypatch, capsys, "replay", "--file", str(tmp_path / "nope.jsonl"))
    _run(monkeypatch, capsys, "surge", "--post-id", "not-a-post-id")
    producer = replay_mod.Producer
    assert not producer.return_value.produce.called


# --- subprocess：真實進入點的 stderr 不可有 traceback ---


@pytest.mark.parametrize(
    "argv",
    [
        ["replay", "--file", "does-not-exist.jsonl"],
        ["replay", "--file", "does-not-exist.jsonl", "--speed=-1"],
        ["record", "--since", "yesterday", "--until", "today", "--out", "x.jsonl"],
        ["surge", "--post-id", "not-a-post-id"],
    ],
)
def test_subprocess_input_errors_have_no_traceback(argv: list[str], tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "radar.streaming.replay", *argv],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "Traceback" not in proc.stdout + proc.stderr


# --- 開發規格 7.20（靜態）---


def _replay_section() -> str:
    text = SPEC.read_text()
    start = text.index("### 7.20 ")
    end = text.index("### 7.21 ")
    section = text[start:end]
    marker = section.index("**錄製與回放**")
    return section[marker:]


def test_spec_replay_states_warmup_condition() -> None:
    s = _replay_section()
    assert "暖機" in s
    assert re.search(r"HEAT_WARMUP_MIN|HEAT_STALE_AFTER_MIN|HEAT_MAX_DELAY_MIN|watermark", s)


def test_spec_replay_states_expected_result() -> None:
    s = _replay_section()
    assert re.search(r"預期|應該(會)?(收到|出現|看到)", s)
    assert "replay.alerts" in s


def test_spec_replay_states_where_to_look() -> None:
    s = _replay_section()
    assert re.search(r"去哪|怎麼看|查看|檢查|消費|kafka-console-consumer|看結果", s)


def test_spec_replay_states_how_to_stop_replay_heat() -> None:
    s = _replay_section()
    assert re.search(r"停掉|停止|關掉|關閉|docker compose[^\n]*(stop|down|rm)", s)


def test_spec_replay_states_what_state_to_clean() -> None:
    s = _replay_section()
    assert re.search(r"清掉|清除|刪除|重置", s)
    assert re.search(r"consumer group|state|volume|內部 topic|changelog", s)

"""tools/bbs_spike.py 的流程層測試（上限與量測邏輯在 tests/unit/acceptance/bbs-spike-tool）。"""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "tests" / "fixtures" / "bbs" / "web_post.html"
URL = "https://www.ptt.cc/bbs/Stock/M.1791600000.A.ABC.html"
NOW = datetime(2026, 11, 10, 13, 10, tzinfo=UTC)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bbs_spike_flow", ROOT / "tools" / "bbs_spike.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load()


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def _ref(post_id: str = "Stock.M.1791600000.A.ABC") -> object:
    return tool.PostRef(URL, post_id, "Stock", "AID", NOW)


def _comment(user: str) -> object:
    return tool.Comment("推", user, "x", datetime(2026, 11, 10, 13, 5, tzinfo=UTC))


def _result(comments: list) -> object:
    return tool.ReadResult(comments, NOW, 12.0, 8, 3, 0)


def _phase_kwargs(clock: Clock, store: object, read: object) -> dict:
    return {
        "read": read,
        "pacer": tool.ReadPacer(clock.now, clock.sleep, uniform=lambda a, b: a),
        "trackers": {"Stock.M.1791600000.A.ABC": tool.CommentTracker("p")},
        "failures": tool.FailureTracker(),
        "store": store,
        "clock": clock.now,
    }


def test_run_phase_records_new_comments_after_baseline(tmp_path: Path) -> None:
    clock, store = Clock(), tool.Store(tmp_path)
    seq = iter([[_comment("a")], [_comment("a"), _comment("b")], [_comment("a"), _comment("b")]])
    tool.run_phase("p1", [_ref()], 40, **_phase_kwargs(clock, store, lambda _r: _result(next(seq))))
    events = [json.loads(ln) for ln in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert len(events) == 1 and events[0]["phase"] == "p1"
    assert len((tmp_path / "reads.jsonl").read_text().splitlines()) == 3


def test_run_phase_unknown_error_stops_with_reason(tmp_path: Path) -> None:
    clock, store = Clock(), tool.Store(tmp_path)

    def read(_r: object) -> object:
        raise type("LoginTooOften", (Exception,), {})("x")

    with pytest.raises(tool.StopExperiment) as info:
        tool.run_phase("p1", [_ref()], 40, **_phase_kwargs(clock, store, read))
    assert info.value.reason == "LoginTooOften"


def test_run_phase_three_read_failures_stop(tmp_path: Path) -> None:
    clock, store = Clock(), tool.Store(tmp_path)

    def read(_r: object) -> object:
        raise type("NoSuchPost", (Exception,), {})()

    with pytest.raises(tool.StopExperiment) as info:
        tool.run_phase("p2", [_ref()], 500, **_phase_kwargs(clock, store, read))
    assert info.value.reason == "consecutive_read_failures"


def test_run_phase_waits_at_least_twenty_seconds_between_reads(tmp_path: Path) -> None:
    clock, store = Clock(), tool.Store(tmp_path)
    tool.run_phase("p1", [_ref()], 40, **_phase_kwargs(clock, store, lambda _r: _result([])))
    reads = (tmp_path / "reads.jsonl").read_text().splitlines()
    assert len(reads) == 3  # t=0、20、40


def test_comments_from_web_fixture_gives_three_comments_in_utc() -> None:
    comments = tool.comments_from_web(FIXTURE.read_text(encoding="utf-8"), URL, NOW)
    assert [c.type for c in comments] == ["推", "噓", "→"]
    assert comments[0].minute == datetime(2026, 11, 10, 5, 5, tzinfo=UTC)


def test_web_poller_reports_only_new_comments_after_first_poll(tmp_path: Path) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    extra = html.replace(
        "</div></div>\n</body>",
        '<div class="push"><span class="f1 hl push-tag">推 </span>'
        '<span class="f3 hl push-userid">user_c</span><span class="f3 push-content">: 新</span>'
        '<span class="push-ipdatetime"> 11/10 13:07</span></div></div></div>\n</body>',
    )
    pages = iter([html, extra])
    poller = tool.WebPoller(
        [_ref()], lambda _u: (200, next(pages)), tool.Store(tmp_path), lambda: NOW
    )
    poller.poll_once()
    poller.poll_once()
    events = [json.loads(ln) for ln in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert len(events) == 1 and events[0]["phase"] == "web"


def test_web_poller_non_200_or_error_is_skipped(tmp_path: Path) -> None:
    calls = iter([(404, ""), (200, "<html></html>")])
    poller = tool.WebPoller([_ref()], lambda _u: next(calls), tool.Store(tmp_path), lambda: NOW)
    poller.poll_once()
    poller.poll_once()
    assert not (tmp_path / "events.jsonl").exists()


def _fake_ptt() -> SimpleNamespace:
    return SimpleNamespace(
        CommentField=SimpleNamespace(type="type", author="author", content="content", time="time"),
        PostField=SimpleNamespace(comments="comments", url="url"),
    )


def test_comments_from_bbs_skips_unparsable_time_and_cleans_text() -> None:
    raw = [
        {
            "type": SimpleNamespace(name="PUSH"),
            "author": "u",
            "content": "\x1b[1mhi",
            "time": "11/10 13:05",
        },
        {"type": SimpleNamespace(name="BOO"), "author": "v", "content": "x", "time": "garbage"},
    ]
    comments, skipped = tool.comments_from_bbs(raw, _fake_ptt(), datetime(2026, 11, 10, tzinfo=UTC))
    assert skipped == 1 and len(comments) == 1
    assert comments[0].type == "推" and comments[0].content == "hi"


def test_bbs_reader_counts_sends_and_stops_on_keyword_screen() -> None:
    clock = Clock()
    ptt = _fake_ptt()
    screens = ["ok"]

    def send(*_a: object, **_k: object) -> int:
        return 0

    core = SimpleNamespace(send=send, get_screen_queue=lambda: screens)
    api = SimpleNamespace(connect_core=core, get_post=lambda *_a, **_k: _post())
    tool.install_send_throttle(api, clock.now, clock.sleep)

    def _post() -> dict:
        api.connect_core.send("k")
        return {"comments": []}

    reader = tool.BbsReader(api, ptt, clock.now, lambda: NOW)
    result, _ = reader.read(_ref())
    assert result.sends == 1 and result.screens == 1
    screens[:] = ["您登入太頻繁"]
    with pytest.raises(tool.StopExperiment):
        reader.read(_ref())


def test_load_credentials_missing_names_variables_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PTT_BBS_USERNAME", raising=False)
    monkeypatch.setenv("PTT_BBS_PASSWORD", "pw-value-123")
    with pytest.raises(SystemExit) as info:
        tool.load_credentials()
    assert "PTT_BBS_USERNAME" in str(info.value)
    assert "pw-value-123" not in str(info.value)


def test_load_credentials_returns_secret_wrapped_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PTT_BBS_USERNAME", "acct")
    monkeypatch.setenv("PTT_BBS_PASSWORD", "pw-value-123")
    user, pw = tool.load_credentials()
    assert user == "acct" and "pw-value-123" not in repr(pw)


def test_parse_post_url_rejects_non_ptt_url() -> None:
    with pytest.raises(SystemExit):
        tool.parse_post_url("https://evil.example/bbs/Stock/M.1.A.AAA.html", _fake_ptt())


def test_parse_post_url_uses_lib_util_for_aid() -> None:
    ptt = SimpleNamespace(lib_util=SimpleNamespace(get_aid_from_url=lambda u: ("Stock", "AID9")))
    ref = tool.parse_post_url(URL, ptt)
    assert ref.aid == "AID9" and ref.post_id == "Stock.M.1791600000.A.ABC"


def test_cmd_run_refuses_without_p0(tmp_path: Path) -> None:
    args = tool.parse_args(["--out", str(tmp_path), "run", "--url", URL, URL, URL])
    assert tool.cmd_run(args) == 3


def test_cmd_summarize_writes_summary_without_ids(tmp_path: Path) -> None:
    run = tmp_path / "r1"
    run.mkdir()
    (tmp_path / "p0.json").write_text(json.dumps({"p0": {"passed": True}}))
    (run / "clock.json").write_text(json.dumps({"offset_seconds": 1.0}))
    ev = [
        {
            "phase": "p2",
            "key": f"k{i}",
            "u": 70,
            "l": 10,
            "e": 40,
            "t": (NOW + timedelta(seconds=i)).isoformat(),
            "post": f"P{i % 2}",
        }
        for i in range(120)
    ] + [
        {
            "phase": "web",
            "key": f"k{i}",
            "u": 400,
            "l": 340,
            "e": 370,
            "t": (NOW + timedelta(seconds=i + 300)).isoformat(),
            "post": "P0",
        }
        for i in range(120)
    ]
    (run / "events.jsonl").write_text("\n".join(json.dumps(e) for e in ev))
    (run / "reads.jsonl").write_text(
        json.dumps({"phase": "p2", "ok": True, "seconds": 7.5, "sends": 8, "screens": 3}) + "\n"
    )
    args = tool.parse_args(
        ["--out", str(tmp_path), "summarize", "--run-id", "r1", "--hot-concurrent-p90", "3"]
    )
    assert tool.cmd_summarize(args) == 0
    summary = json.loads((run / "summary.json").read_text())
    assert summary["decision"]["recommend"] is True
    assert summary["capacity"]["n_max"] == 4
    assert summary["web_pairing"]["diff_p50"] == 300
    assert summary["clock_offset_flag"] is False

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


def test_ledger_update_last_changes_result_without_adding_attempt(tmp_path: Path) -> None:
    ledger = tool.Ledger(tmp_path / "l.jsonl")
    ledger.record(NOW, "attempt")
    ledger.record(NOW + timedelta(minutes=11), "attempt")
    ledger.update_last("ok")
    lines = [json.loads(ln) for ln in (tmp_path / "l.jsonl").read_text().splitlines()]
    assert [r["result"] for r in lines] == ["attempt", "ok"]
    assert len(ledger.attempts()) == 2


# ---------- architect review：登入畫面、URL 先驗證、web 列同一批 ----------

SECRET_ID = "sentinel_acct_01"
SECRET_PW = "sentinel-pw-0042"
GOOD_URL = "https://www.ptt.cc/bbs/Stock/M.1700000000.A.123.html"


def _fake_pyptt(screens: list[str] | None, aid_error: bool = False) -> SimpleNamespace:
    state = SimpleNamespace(logouts=0, logins=0)

    class Api:
        def __init__(self, **_: object) -> None:
            queue = SimpleNamespace(get=lambda n: (screens or [])[-n:])
            self.connect_core = SimpleNamespace(
                send=lambda *_a, **_k: None,
                get_screen_queue=lambda: [],
                **({"_RDQ": queue} if screens is not None else {}),
            )

        def login(self, *_a: object, **_k: object) -> None:
            state.logins += 1

        def logout(self) -> None:
            state.logouts += 1

        def get_post(self, *_a: object, **_k: object) -> dict:
            raise RuntimeError("stop here")

    def aid(_url: str) -> tuple[str, str]:
        if aid_error:
            raise ValueError("bad")
        return "Stock", "1Zzzzzzz"

    return SimpleNamespace(
        API=Api,
        LogLevel=SimpleNamespace(SILENT=0),
        PostField=SimpleNamespace(url="url", comments="comments"),
        CommentField=SimpleNamespace(time="time", ip="ip"),
        lib_util=SimpleNamespace(get_aid_from_url=aid),
        state=state,
    )


def _probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ptt: SimpleNamespace, url: str) -> int:
    monkeypatch.setitem(__import__("sys").modules, "PyPtt", ptt)
    monkeypatch.setenv("PTT_BBS_USERNAME", SECRET_ID)
    monkeypatch.setenv("PTT_BBS_PASSWORD", SECRET_PW)
    monkeypatch.setattr(tool.time, "sleep", lambda _s: None)
    args = tool.parse_args(["--out", str(tmp_path / "out"), "probe", "--url", url])
    return tool.cmd_probe(args)


def test_probe_login_screen_with_too_often_keyword_logs_out_and_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ptt = _fake_pyptt(["主選單", "您登入太頻繁，請稍後"])
    code = _probe(monkeypatch, tmp_path, ptt, GOOD_URL)
    assert code != 0
    assert ptt.state.logouts == 1
    ledger = (tmp_path / "out" / "ledger.jsonl").read_text()
    assert "screen_keyword" in ledger and "failed" in ledger
    assert not (tmp_path / "out" / "p0.json").read_text().count('"passed": true')


def test_probe_clean_login_screens_continue_to_reading(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ptt = _fake_pyptt(["主選單"])
    _probe(monkeypatch, tmp_path, ptt, GOOD_URL)
    assert '"ok"' in (tmp_path / "out" / "ledger.jsonl").read_text()


def test_probe_without_screen_queue_skips_login_screen_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ptt = _fake_pyptt(None)
    _probe(monkeypatch, tmp_path, ptt, GOOD_URL)
    assert ptt.state.logins == 1


@pytest.mark.parametrize("bad", ["https://evil.example/bbs/Stock/M.1.A.AAA.html", "nonsense"])
def test_probe_invalid_url_exits_before_login_and_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, bad: str
) -> None:
    ptt = _fake_pyptt(["ok"])
    with pytest.raises(SystemExit):
        _probe(monkeypatch, tmp_path, ptt, bad)
    assert ptt.state.logins == 0
    assert not (tmp_path / "out" / "ledger.jsonl").exists()


def test_probe_aid_conversion_error_exits_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ptt = _fake_pyptt(["ok"], aid_error=True)
    with pytest.raises(SystemExit):
        _probe(monkeypatch, tmp_path, ptt, GOOD_URL)
    assert ptt.state.logins == 0
    assert not (tmp_path / "out" / "ledger.jsonl").exists()


def test_run_invalid_url_exits_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ptt = _fake_pyptt(["ok"])
    monkeypatch.setitem(__import__("sys").modules, "PyPtt", ptt)
    monkeypatch.setenv("PTT_BBS_USERNAME", SECRET_ID)
    monkeypatch.setenv("PTT_BBS_PASSWORD", SECRET_PW)
    out = tmp_path / "out"
    out.mkdir()
    (out / "p0.json").write_text(json.dumps({"p0": {"passed": True}}))
    args = tool.parse_args(["--out", str(out), "run", "--url", GOOD_URL, GOOD_URL, "bad"])
    with pytest.raises(SystemExit):
        tool.cmd_run(args)
    assert ptt.state.logins == 0 and not (out / "ledger.jsonl").exists()


def test_recent_screens_prefers_rdq_ten_screens_over_single_queue() -> None:
    rdq = SimpleNamespace(get=lambda n: [f"s{i}" for i in range(n)])
    core = SimpleNamespace(_RDQ=rdq, get_screen_queue=lambda: ["only"])
    assert len(tool.recent_screens(SimpleNamespace(connect_core=core))) == 10


def test_summarize_web_row_keeps_only_keys_seen_on_bbs(tmp_path: Path) -> None:
    run = tmp_path / "r2"
    run.mkdir()
    (tmp_path / "p0.json").write_text(json.dumps({"p0": {"passed": True}}))
    (run / "clock.json").write_text(json.dumps({"offset_seconds": 0}))

    def rec(phase: str, key: str) -> dict:
        return {
            "phase": phase,
            "key": key,
            "u": 1,
            "l": 0,
            "e": -29,
            "t": NOW.isoformat(),
            "post": "P",
        }

    rows = [rec("p2", "a"), rec("web", "a"), rec("web", "only-web-1"), rec("web", "only-web-2")]
    (run / "events.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    args = tool.parse_args(
        ["--out", str(tmp_path), "summarize", "--run-id", "r2", "--hot-concurrent-p90", "1"]
    )
    tool.cmd_summarize(args)
    summary = json.loads((run / "summary.json").read_text())
    assert summary["web"]["samples"] == 1

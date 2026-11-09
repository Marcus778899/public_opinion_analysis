"""bbs-spike-tool 驗收測試（開發規格 7.31 B、C、威脅與對策）。

只測 tools/bbs_spike.py 對外的行為；全部用假時鐘、假 PyPtt、假資料，不連真實 PTT。
模組須提供的介面（名稱即契約）見各測試使用處；PyPtt 必須延遲 import。
"""

import importlib.util
import json
import re
import sys
import tomllib
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
SECRET_PW = "S3ntinel-pw-9f2c"
SECRET_ID = "sentinel_account_77"
T0 = datetime(2026, 11, 10, 13, 0, 0, tzinfo=UTC)


def _load() -> ModuleType:
    sys.modules.pop("PyPtt", None)
    path = ROOT / "tools" / "bbs_spike.py"
    spec = importlib.util.spec_from_file_location("bbs_spike_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load()


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds


# ---------- 常數（7.31 B 上限）----------


def test_limits_are_constants_with_spec_values() -> None:
    assert tool.MAX_LOGINS == 3
    assert tool.MIN_LOGIN_INTERVAL_SECONDS == 600
    assert tool.MIN_READ_INTERVAL_SECONDS == 20
    assert tool.READ_JITTER_MAX_SECONDS == 5
    assert tool.MIN_SEND_INTERVAL_SECONDS == 1
    assert tool.WEB_POLL_INTERVAL_SECONDS == 60
    assert tool.MAX_CONSECUTIVE_READ_FAILURES == 3
    assert tool.P0_MAX_SECONDS_PER_POST == 120
    assert tool.P0_MAX_SENDS_PER_POST == 120


def test_module_import_does_not_import_pyptt() -> None:
    assert "PyPtt" not in sys.modules


# ---------- ledger：登入次數與間隔 ----------


def test_ledger_records_attempts_and_reloads(tmp_path: Path) -> None:
    ledger = tool.Ledger(tmp_path / "ledger.jsonl")
    ledger.record(T0, "ok")
    ledger.record(T0 + timedelta(minutes=11), "fail")
    again = tool.Ledger(tmp_path / "ledger.jsonl")
    assert again.attempts() == [T0, T0 + timedelta(minutes=11)]


def test_login_allowed_when_no_attempts() -> None:
    tool.check_login_allowed([], T0)


def test_login_refused_after_three_attempts_even_if_failed() -> None:
    attempts = [T0, T0 + timedelta(minutes=11), T0 + timedelta(minutes=22)]
    with pytest.raises(tool.LoginRefused):
        tool.check_login_allowed(attempts, T0 + timedelta(hours=2))


def test_login_refused_within_ten_minutes_of_last_attempt() -> None:
    with pytest.raises(tool.LoginRefused):
        tool.check_login_allowed([T0], T0 + timedelta(minutes=10) - timedelta(seconds=1))


def test_login_allowed_exactly_ten_minutes_after_last_attempt() -> None:
    tool.check_login_allowed([T0], T0 + timedelta(minutes=10))


def test_login_allowed_on_third_attempt() -> None:
    tool.check_login_allowed([T0, T0 + timedelta(minutes=11)], T0 + timedelta(minutes=30))


# ---------- 讀取與 send 節流 ----------


def test_read_pacer_waits_at_least_twenty_seconds_between_reads() -> None:
    clock = FakeClock()
    pacer = tool.ReadPacer(clock.now, clock.sleep, uniform=lambda a, b: a)
    pacer.mark_done()
    pacer.wait()
    assert sum(clock.sleeps) == pytest.approx(20)


def test_read_pacer_adds_jitter_between_zero_and_five() -> None:
    clock = FakeClock()
    seen: list[tuple[float, float]] = []

    def uniform(a: float, b: float) -> float:
        seen.append((a, b))
        return b

    pacer = tool.ReadPacer(clock.now, clock.sleep, uniform=uniform)
    pacer.mark_done()
    pacer.wait()
    assert seen == [(0, 5)]
    assert sum(clock.sleeps) == pytest.approx(25)


def test_read_pacer_counts_time_already_elapsed() -> None:
    clock = FakeClock()
    pacer = tool.ReadPacer(clock.now, clock.sleep, uniform=lambda a, b: a)
    pacer.mark_done()
    clock.t += 15
    pacer.wait()
    assert sum(clock.sleeps) == pytest.approx(5)


def test_read_pacer_first_read_does_not_wait() -> None:
    clock = FakeClock()
    tool.ReadPacer(clock.now, clock.sleep).wait()
    assert clock.sleeps == []


def _fake_api(login_exc: Exception | None = None) -> SimpleNamespace:
    calls: list[str] = []

    def original_send(*args: object, **kwargs: object) -> str:
        calls.append("send")
        return "screen"

    connect_core = SimpleNamespace(send=original_send)
    state = SimpleNamespace(
        login_calls=[], log_level=None, original_send=original_send, send_during_login=None
    )

    def login(*args: object, **kwargs: object) -> None:
        state.login_calls.append((args, kwargs))
        state.send_during_login = connect_core.send
        if login_exc is not None:
            raise login_exc

    api = SimpleNamespace(connect_core=connect_core, login=login, state=state, calls=calls)
    return api


def _fake_ptt(api: SimpleNamespace) -> SimpleNamespace:
    def make_api(**kwargs: object) -> SimpleNamespace:
        api.state.log_level = kwargs.get("log_level")
        return api

    return SimpleNamespace(API=make_api, LogLevel=SimpleNamespace(SILENT="SILENT-SENTINEL"))


def test_send_throttle_enforces_one_second_between_sends() -> None:
    clock = FakeClock()
    api = _fake_api()
    throttle = tool.install_send_throttle(api, clock.now, clock.sleep)
    api.connect_core.send("a")
    api.connect_core.send("b")
    assert sum(clock.sleeps) >= 1
    assert throttle.count == 2
    assert api.calls == ["send", "send"]


def test_send_throttle_does_not_sleep_when_gap_is_enough() -> None:
    clock = FakeClock()
    api = _fake_api()
    tool.install_send_throttle(api, clock.now, clock.sleep)
    api.connect_core.send("a")
    clock.t += 2
    api.connect_core.send("b")
    assert clock.sleeps == []


def test_open_session_wraps_send_only_after_login() -> None:
    clock = FakeClock()
    api = _fake_api()
    session_api = tool.open_session(
        _fake_ptt(api), SECRET_ID, tool.SecretStr(SECRET_PW), clock.now, clock.sleep
    )
    assert session_api is api
    assert api.state.send_during_login is api.state.original_send
    assert api.connect_core.send is not api.state.original_send


def test_open_session_passes_kick_other_session_false_and_silent_log() -> None:
    clock = FakeClock()
    api = _fake_api()
    tool.open_session(_fake_ptt(api), SECRET_ID, tool.SecretStr(SECRET_PW), clock.now, clock.sleep)
    assert api.state.log_level == "SILENT-SENTINEL"
    assert len(api.state.login_calls) == 1
    args, kwargs = api.state.login_calls[0]
    assert kwargs["kick_other_session"] is False
    assert SECRET_PW in (*args, *kwargs.values())


class ConnectError(Exception):
    pass


def test_login_failure_is_not_retried() -> None:
    clock = FakeClock()
    api = _fake_api(ConnectError("boom"))
    with pytest.raises((tool.BbsLoginError, tool.StopExperiment)):
        tool.open_session(
            _fake_ptt(api), SECRET_ID, tool.SecretStr(SECRET_PW), clock.now, clock.sleep
        )
    assert len(api.state.login_calls) == 1


# ---------- 立即停止 ----------


@pytest.mark.parametrize(
    "name",
    ["UseTooManyResources", "LoginTooOften", "UserHasPreviouslyBeenBanned", "WrongIDorPassword"],
)
def test_stop_reason_names_the_listed_pyptt_exceptions(name: str) -> None:
    exc = type(name, (Exception,), {})("detail")
    assert tool.stop_reason(exc) == name


def test_stop_reason_unrecognized_error_still_stops() -> None:
    assert tool.stop_reason(ValueError("x")) == "unrecognized_error"


@pytest.mark.parametrize("text", ["您登入太頻繁，請稍後再試", "目前系統過載，請稍後"])
def test_screen_with_stop_keyword_raises_stop(text: str) -> None:
    with pytest.raises(tool.StopExperiment):
        tool.check_screens(["normal screen", text])


def test_normal_screens_do_not_stop() -> None:
    tool.check_screens(["文章列表", "推 someone: hi"])


def test_three_consecutive_read_failures_stop() -> None:
    tracker = tool.FailureTracker()
    tracker.record(ok=False)
    tracker.record(ok=False)
    with pytest.raises(tool.StopExperiment):
        tracker.record(ok=False)


def test_success_resets_consecutive_failure_count() -> None:
    tracker = tool.FailureTracker()
    for ok in (False, False, True, False, False):
        tracker.record(ok=ok)


# ---------- P0 閘門 ----------


def test_p0_pass_requires_all_checks() -> None:
    kw = {
        "login_ok": True,
        "aid_ok": True,
        "boards_ok": {"Stock": True},
        "seconds": [30.0],
        "sends": [40],
    }
    assert tool.evaluate_p0(**kw) is True


@pytest.mark.parametrize(
    "override",
    [
        {"login_ok": False},
        {"aid_ok": False},
        {"boards_ok": {"Stock": False, "Gossiping": False}},
        {"seconds": [120.1]},
        {"sends": [121]},
    ],
)
def test_p0_fails_when_any_check_fails(override: dict[str, object]) -> None:
    kw = {
        "login_ok": True,
        "aid_ok": True,
        "boards_ok": {"Stock": True},
        "seconds": [30.0],
        "sends": [40],
    }
    kw.update(override)
    assert tool.evaluate_p0(**kw) is False


def test_p0_limits_are_inclusive() -> None:
    kw = {
        "login_ok": True,
        "aid_ok": True,
        "boards_ok": {"Stock": True},
        "seconds": [120.0],
        "sends": [120],
    }
    assert tool.evaluate_p0(**kw) is True


def test_run_refused_when_p0_missing_or_failed() -> None:
    with pytest.raises(tool.P0NotPassed):
        tool.require_p0({})
    with pytest.raises(tool.P0NotPassed):
        tool.require_p0({"p0": {"passed": False}})
    tool.require_p0({"p0": {"passed": True}})


# ---------- C：U / L / E ----------

MIN_T = datetime(2026, 11, 10, 13, 5, tzinfo=UTC)


def _c(user: str = "u1", content: str = "hi", minute: datetime = MIN_T, type_: str = "推"):
    return tool.Comment(type=type_, user_id=user, content=content, minute=minute)


def test_ule_values_for_comment_seen_ninety_seconds_after_minute() -> None:
    u, low, e = tool.compute_ule(MIN_T, MIN_T + timedelta(seconds=90))
    assert (u, low, e) == (90, 30, 60)


def test_ule_lower_bound_is_clamped_at_zero() -> None:
    u, low, e = tool.compute_ule(MIN_T, MIN_T + timedelta(seconds=20))
    assert (u, low, e) == (20, 0, -10)


def test_ule_negative_upper_when_seen_before_labeled_minute() -> None:
    u, low, _ = tool.compute_ule(MIN_T, MIN_T - timedelta(seconds=5))
    assert u == -5
    assert low == 0


def test_first_read_is_baseline_and_counts_nothing() -> None:
    tracker = tool.CommentTracker()
    assert tracker.observe([_c("a"), _c("b")], MIN_T + timedelta(seconds=100)) == []


def test_new_comment_after_baseline_is_reported_with_ule() -> None:
    tracker = tool.CommentTracker()
    tracker.observe([_c("a")], MIN_T)
    events = tracker.observe([_c("a"), _c("b")], MIN_T + timedelta(seconds=70))
    assert len(events) == 1
    assert (events[0].u, events[0].l, events[0].e) == (70, 10, 40)


def test_known_comment_is_not_reported_twice() -> None:
    tracker = tool.CommentTracker()
    tracker.observe([_c("a")], MIN_T)
    tracker.observe([_c("a"), _c("b")], MIN_T + timedelta(seconds=70))
    assert tracker.observe([_c("a"), _c("b")], MIN_T + timedelta(seconds=90)) == []


def test_deleting_earlier_comment_does_not_duplicate_later_ones() -> None:
    tracker = tool.CommentTracker()
    tracker.observe([_c("a"), _c("b"), _c("c")], MIN_T)
    assert tracker.observe([_c("b"), _c("c")], MIN_T + timedelta(seconds=40)) == []


def test_identical_comments_same_minute_are_distinguished_by_occurrence() -> None:
    tracker = tool.CommentTracker()
    tracker.observe([_c("a", "推")], MIN_T)
    events = tracker.observe([_c("a", "推"), _c("a", "推")], MIN_T + timedelta(seconds=50))
    assert len(events) == 1
    events = tracker.observe(
        [_c("a", "推"), _c("a", "推"), _c("a", "推")], MIN_T + timedelta(seconds=80)
    )
    assert len(events) == 1


def test_content_whitespace_is_normalized_for_identity() -> None:
    tracker = tool.CommentTracker()
    tracker.observe([_c("a", "hello  world")], MIN_T)
    assert tracker.observe([_c("a", " hello world ")], MIN_T + timedelta(seconds=40)) == []


def test_different_type_or_minute_is_a_different_comment() -> None:
    tracker = tool.CommentTracker()
    tracker.observe([_c("a")], MIN_T)
    later = MIN_T + timedelta(seconds=100)
    events = tracker.observe(
        [_c("a"), _c("a", type_="噓"), _c("a", minute=MIN_T + timedelta(minutes=1))], later
    )
    assert len(events) == 2


# ---------- C：p50、網頁版配對 ----------


def test_p50_of_odd_sample_is_middle_value() -> None:
    assert tool.p50([5, 1, 3]) == 3


def test_web_pairing_diff_p50_and_not_appeared() -> None:
    bbs = {f"k{i}": MIN_T + timedelta(seconds=10 * i) for i in range(10)}
    web = {f"k{i}": bbs[f"k{i}"] + timedelta(seconds=300 + i) for i in range(8)}
    cmp_ = tool.pair_with_web(bbs, web)
    assert cmp_.diff_p50 == 304
    assert cmp_.not_appeared == 2
    assert cmp_.unmatched_ratio == pytest.approx(0.2)
    assert cmp_.usable is False


def test_web_pairing_usable_when_unmatched_at_most_ten_percent() -> None:
    bbs = {f"k{i}": MIN_T for i in range(10)}
    web = {f"k{i}": MIN_T + timedelta(seconds=100) for i in range(9)}
    assert tool.pair_with_web(bbs, web).usable is True


def test_web_pairing_not_appeared_is_counted_not_dropped() -> None:
    cmp_ = tool.pair_with_web({"k": MIN_T}, {})
    assert cmp_.not_appeared == 1


# ---------- C：樣本下限與門檻 ----------


def test_sample_floor_p1_needs_thirty() -> None:
    assert tool.sample_ok("p1", samples=30, posts=1) is True
    assert tool.sample_ok("p1", samples=29, posts=1) is False


def test_sample_floor_p2_needs_hundred_from_two_posts() -> None:
    assert tool.sample_ok("p2", samples=100, posts=2) is True
    assert tool.sample_ok("p2", samples=99, posts=3) is False
    assert tool.sample_ok("p2", samples=500, posts=1) is False


def test_needed_connections_uses_n_max_formula() -> None:
    # N_max = floor(120 / (7.5 + 22.5)) = 4
    assert tool.n_max(7.5) == 4
    assert tool.needed_connections(7.5, hot_concurrent_p90=4) == 1
    assert tool.needed_connections(7.5, hot_concurrent_p90=5) == 2
    # N_max = floor(120 / (30 + 22.5)) = 2
    assert tool.needed_connections(30, hot_concurrent_p90=5) == 3


def _decide(**over: object):
    kw = {
        "p2_e_p50": 34.0,
        "p2_samples": 150,
        "p2_posts": 3,
        "connections_needed": 1,
        "connections_proven": 1,
        "forbidden": False,
        "stop_triggered": False,
    }
    kw.update(over)
    return tool.decide(**kw)


def test_decision_recommends_when_all_criteria_hold() -> None:
    assert _decide().recommend is True


def test_decision_p50_sixty_is_accepted_and_above_is_not() -> None:
    assert _decide(p2_e_p50=60.0).recommend is True
    assert _decide(p2_e_p50=60.1).recommend is False


def test_decision_insufficient_samples_means_not_recommended() -> None:
    assert _decide(p2_samples=99).recommend is False
    assert _decide(p2_posts=1).recommend is False


def test_decision_needs_connections_within_proven() -> None:
    assert _decide(connections_needed=2, connections_proven=1).recommend is False
    assert _decide(connections_needed=2, connections_proven=3).recommend is True


def test_decision_rules_forbidden_or_stop_triggered_means_not_recommended() -> None:
    assert _decide(forbidden=True).recommend is False
    assert _decide(stop_triggered=True).recommend is False


def test_decision_rules_unconfirmed_still_passes_that_criterion() -> None:
    assert _decide(forbidden=None).recommend is True


# ---------- 秘密保護 ----------


def test_login_error_does_not_leak_password_or_id() -> None:
    clock = FakeClock()
    api = _fake_api(ConnectError(f"cannot login {SECRET_ID} {SECRET_PW}"))
    with pytest.raises((tool.BbsLoginError, tool.StopExperiment)) as info:
        tool.open_session(
            _fake_ptt(api), SECRET_ID, tool.SecretStr(SECRET_PW), clock.now, clock.sleep
        )
    exc = info.value
    rendered = "".join(traceback.format_exception(exc)) + str(exc) + repr(exc)
    assert SECRET_PW not in rendered
    assert SECRET_ID not in rendered
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True
    assert "ConnectError" in str(exc)


def test_secret_not_in_logs_or_stdout_when_login_fails(capsys: pytest.CaptureFixture[str]) -> None:
    clock = FakeClock()
    api = _fake_api(ConnectError(f"{SECRET_PW}"))
    with pytest.raises((tool.BbsLoginError, tool.StopExperiment)):
        tool.open_session(
            _fake_ptt(api), SECRET_ID, tool.SecretStr(SECRET_PW), clock.now, clock.sleep
        )
    out = capsys.readouterr()
    assert SECRET_PW not in out.out + out.err


def test_secretstr_masks_in_repr() -> None:
    assert SECRET_PW not in repr(tool.SecretStr(SECRET_PW))


def test_scan_and_purge_deletes_files_containing_secret(tmp_path: Path) -> None:
    clean = tmp_path / "clean.json"
    dirty = tmp_path / "sub" / "dirty.txt"
    dirty.parent.mkdir()
    clean.write_text("nothing here")
    dirty.write_text(f"oops {SECRET_PW}")
    removed = tool.scan_and_purge(tmp_path, [SECRET_PW, SECRET_ID])
    assert removed == [dirty]
    assert clean.exists()
    assert not dirty.exists()


def test_scan_and_purge_catches_the_id_too_and_ignores_empty_secret(tmp_path: Path) -> None:
    f = tmp_path / "a.txt"
    f.write_text(f"id={SECRET_ID}")
    assert tool.scan_and_purge(tmp_path, ["", SECRET_ID]) == [f]


def test_finish_exits_nonzero_and_names_only_variables_when_leak(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "a.txt").write_text(SECRET_PW)
    code = tool.finish_output_check(tmp_path, SECRET_ID, SECRET_PW)
    out = capsys.readouterr()
    assert code != 0
    assert SECRET_PW not in out.out + out.err
    assert "PTT_BBS_PASSWORD" in out.out + out.err


def test_finish_exits_zero_when_output_is_clean(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("ok")
    assert tool.finish_output_check(tmp_path, SECRET_ID, SECRET_PW) == 0


def test_sanitize_screen_strips_control_and_ansi_sequences() -> None:
    raw = "\x1b[1;33m推\x1b[m user\x07: text\x00\r\n"
    cleaned = tool.sanitize_screen(raw)
    assert "\x1b" not in cleaned
    assert "\x07" not in cleaned
    assert "\x00" not in cleaned
    assert "推" in cleaned and "text" in cleaned


# ---------- summary.json ----------


def _events(prefix: str, n: int, base: float = 40.0) -> list:
    out = []
    for i in range(n):
        c = tool.Comment(
            type="推",
            user_id=f"{SECRET_ID}_{prefix}{i}",
            content=f"private words {prefix}{i}",
            minute=MIN_T,
        )
        t = MIN_T + timedelta(seconds=base + 30 + i % 5)
        out.append(tool.make_event(c, t))
    return out


def test_summary_has_no_user_ids_or_comment_text() -> None:
    summary = tool.build_summary(
        p1=_events("a", 31), p2=_events("b", 120), web=_events("c", 20), p0={"passed": True}
    )
    text = json.dumps(summary, ensure_ascii=False)
    assert SECRET_ID not in text
    assert "private words" not in text


def test_summary_reports_samples_and_p50_for_each_phase() -> None:
    summary = tool.build_summary(
        p1=_events("a", 31), p2=_events("b", 120), web=_events("c", 20), p0={"passed": True}
    )
    for phase, n in (("p1", 31), ("p2", 120), ("web", 20)):
        entry = summary[phase]
        assert entry["samples"] == n
        for key in ("p50_l", "p50_e", "p50_u"):
            assert key in entry
    assert summary["p0"] == {"passed": True}


def test_summary_marks_insufficient_samples() -> None:
    summary = tool.build_summary(
        p1=_events("a", 5), p2=_events("b", 120), web=[], p0={"passed": True}
    )
    assert summary["p1"]["sample_ok"] is False


# ---------- 相依與設定檔 ----------


def test_pyptt_pinned_only_in_bbs_spike_group() -> None:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    groups = data["dependency-groups"]
    assert any(re.fullmatch(r"(?i)pyptt\s*==\s*2\.3\.16", d) for d in groups["bbs-spike"])
    for name, deps in groups.items():
        if name != "bbs-spike":
            assert not any("pyptt" in str(d).lower() for d in deps)
    assert not any("pyptt" in d.lower() for d in data["project"].get("dependencies", []))


def test_env_example_ptt_bbs_vars_are_uncommented_with_empty_values() -> None:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "PTT_BBS_USERNAME=" in lines
    assert "PTT_BBS_PASSWORD=" in lines
    assert not any(re.match(r"\s*#\s*PTT_BBS_(USERNAME|PASSWORD)=", ln) for ln in lines)
    idx = lines.index("PTT_BBS_USERNAME=")
    assert lines[idx - 1].lstrip().startswith("#"), "要保留說明註解"


def test_tool_has_no_hardcoded_credentials_or_cli_password_option() -> None:
    src = (ROOT / "tools" / "bbs_spike.py").read_text(encoding="utf-8")
    assert "PTT_BBS_USERNAME" in src and "PTT_BBS_PASSWORD" in src
    assert "--password" not in src and "--username" not in src
    assert not re.search(r"^\s*print\(", src, re.M), "log 一律用 radar.common.log"


# ---------- 回歸：ledger 結果欄位、7.31 B 甲方執行指令 ----------


class _LoginError(Exception):
    pass


def _fake_pyptt_module(login_error: Exception | None) -> SimpleNamespace:
    class Api:
        def __init__(self, **_: object) -> None:
            self.connect_core = SimpleNamespace(
                send=lambda *_a, **_k: None, get_screen_queue=lambda: []
            )

        def login(self, *_a: object, **_k: object) -> None:
            if login_error is not None:
                raise login_error

        def logout(self) -> None:
            return None

        def get_post(self, *_a: object, **_k: object) -> dict:
            raise RuntimeError("stop here")

    return SimpleNamespace(
        API=Api,
        LogLevel=SimpleNamespace(SILENT=0),
        PostField=SimpleNamespace(url="url", comments="comments"),
        CommentField=SimpleNamespace(time="time", ip="ip"),
        lib_util=SimpleNamespace(get_aid_from_url=lambda url: ("Stock", "1Zzzzzzz")),
    )


def _run_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, login_error: Exception | None
) -> list[dict]:
    monkeypatch.setitem(sys.modules, "PyPtt", _fake_pyptt_module(login_error))
    monkeypatch.setenv("PTT_BBS_USERNAME", SECRET_ID)
    monkeypatch.setenv("PTT_BBS_PASSWORD", SECRET_PW)
    monkeypatch.setattr(tool.time, "sleep", lambda _s: None)
    out = tmp_path / "out"
    url = "https://www.ptt.cc/bbs/Stock/M.1700000000.A.123.html"
    monkeypatch.setattr(sys, "argv", ["bbs_spike.py", "--out", str(out), "probe", "--url", url])
    with pytest.raises(SystemExit):
        tool.main()
    lines = (out / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(ln) for ln in lines if ln.strip()]


def test_probe_login_failure_updates_ledger_result_from_attempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    records = _run_probe(monkeypatch, tmp_path, _LoginError(f"{SECRET_ID} {SECRET_PW}"))
    assert records[-1]["result"] != "attempt"
    assert "fail" in records[-1]["result"].lower()
    assert SECRET_PW not in json.dumps(records) and SECRET_ID not in json.dumps(records)


def test_probe_login_success_updates_ledger_result_to_ok(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    records = _run_probe(monkeypatch, tmp_path, None)
    assert records[-1]["result"] != "attempt"
    assert "ok" in records[-1]["result"].lower()


def test_probe_one_login_counts_as_one_attempt_in_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _run_probe(monkeypatch, tmp_path, None)
    assert len(tool.Ledger(tmp_path / "out" / "ledger.jsonl").attempts()) == 1


def _spec_section_b() -> str:
    text = (ROOT / "docs" / "development-spec.md").read_text(encoding="utf-8")
    start = text.index("### 7.31 ")
    b = text.index("#### B.", start)
    c = text.index("#### C.", b)
    return text[b:c]


@pytest.mark.parametrize(
    ("sub", "options"),
    [
        ("probe", ["--url"]),
        ("run", ["--url", "--tail-minutes"]),
        ("summarize", ["--run-id", "--hot-concurrent-p90", "--rules", "--connections-proven"]),
    ],
)
def test_spec_731_b_has_runnable_command_per_subcommand(sub: str, options: list[str]) -> None:
    section = _spec_section_b()
    lines = [ln for ln in section.splitlines() if "bbs_spike.py" in ln and f" {sub}" in ln]
    assert lines, f"7.31 B 缺 {sub} 的完整指令"
    assert any("uv run" in ln for ln in lines)
    for opt in options:
        assert opt in section, f"7.31 B 沒說明 {opt}"
    assert "--out" in section


def test_spec_731_b_commands_hold_no_credential_values() -> None:
    section = _spec_section_b()
    assert "--password" not in section and "--username" not in section

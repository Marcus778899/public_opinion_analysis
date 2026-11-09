"""bbs-retest-tool 驗收測試（開發規格 7.31 G；B、C 沿用）。

全部用假時鐘、假 PyPtt、假網頁版與手寫資料，不連真實 PTT、不讀 .env；沒裝 bbs-spike group 也能跑
（PyPtt 只以 sys.modules 注入假模組）。

介面約定（測試依這些名稱，規格沒寫死的部分由本檔定義，worker 若有出入請回報由 manager 仲裁）：
- `tool.COMMANDS["retest"|"summarize-retest"]`，參數 `--url`(4)、`--connections`、`--p0`、`--out`、
  `--run-id`、`--hot-concurrent-p90`、`--rules`
- 登入前檢查不過：回傳或 SystemExit 碼 3，沒有任何 PyPtt API 被建立，也沒寫 ledger
- 輸出：`<out>/ledger.jsonl`（每筆有 `at`、`result`、`conn`）、`<out>/<run_id>/` 內的
  `meta.json`、`events.jsonl`、`reads.jsonl`（phase 為 `r2`／`m`／`web`）、`connections.json`
  與 summary 的 `r2`（同 first-run 的 `p2`：samples、posts、p50_e…）
- `connections.json` 與 summary 的 `connections`：
  `{"tested": int, "proven": int, "stop_reason": str | None}`
- summary：`decision.recommend`、`excluded`（`post_id`、`reason`）、`capacity`／`capacity_all`
"""

import importlib.util
import json
import logging
import re
import socket
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[4]
SECRET_PW = "S3ntinel-pw-9f2c"
SECRET_ID = "sentinel_account_77"
START = datetime(2026, 11, 10, 12, 10, 0, tzinfo=UTC)  # 20:10 Asia/Taipei
RUN_ID = "20261110T121000Z"
MONO0 = 1000.0


def _load() -> ModuleType:
    sys.modules.pop("PyPtt", None)
    spec = importlib.util.spec_from_file_location(
        "bbs_retest_under_test", ROOT / "tools" / "bbs_spike.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = _load()


class ConnectionClosed(Exception):
    pass


class LoginFailed(Exception):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise OSError("network is blocked in unit tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def test_module_import_does_not_import_pyptt() -> None:
    assert "PyPtt" not in sys.modules


# ---------- 假世界：時鐘、PyPtt、網頁版 ----------


def _taipei_label(utc: datetime) -> str:
    return (utc + timedelta(hours=8)).strftime("%m/%d %H:%M")


def _page(pushes: list[tuple[str, str, str, str]]) -> str:
    head = (
        '<html><head><title>x</title></head><body><div id="main-content" class="bbs-screen">'
        '<div class="article-metaline"><span class="article-meta-tag">作者</span>'
        '<span class="article-meta-value">a1 (n)</span></div>'
        '<div class="article-metaline-right"><span class="article-meta-tag">看板</span>'
        '<span class="article-meta-value">Stock</span></div>'
        '<div class="article-metaline"><span class="article-meta-tag">標題</span>'
        '<span class="article-meta-value">[閒聊] t</span></div>'
        '<div class="article-metaline"><span class="article-meta-tag">時間</span>'
        '<span class="article-meta-value">Tue Nov 10 19:40:00 2026</span></div>body\n'
    )
    rows = "".join(
        f'<div class="push"><span class="hl push-tag">{tag} </span>'
        f'<span class="f3 hl push-userid">{user}</span>'
        f'<span class="f3 push-content">: {content}</span>'
        f'<span class="push-ipdatetime"> {label}\n</span></div>'
        for tag, user, content, label in pushes
    )
    return head + rows + "</div></body></html>"


@dataclass
class Scenario:
    start: datetime = START
    boards: tuple[str, ...] = ("Stock", "Gossiping", "Tech_Job", "Stock")
    ages: tuple[float, ...] = (1800, 1800, 1800, 1800)  # 發文距 start 幾秒
    history: tuple[tuple[int, int], ...] = ((40, 0),) * 4  # 每篇（推, 噓）
    interval: float = 10.0  # 每篇每幾秒一則新推文
    onset: float = 0.0  # start 之後多久才開始有新推文
    active: tuple[int, ...] = (0, 1, 2, 3)
    login_errors: dict[int, Exception] = field(default_factory=dict)
    login_screens: dict[int, list[str]] = field(default_factory=dict)
    read_error: Callable[[int, "World"], Exception | None] | None = None
    read_screens: Callable[[int, "World"], list[str]] | None = None


class World:
    def __init__(self, sc: Scenario) -> None:
        self.sc = sc
        self.mono = MONO0
        self.events: list[tuple[float, str, int, object]] = []
        self.apis: list[FakeApi] = []
        self.urls = [
            f"https://www.ptt.cc/bbs/{b}/M.{int(sc.start.timestamp() - sc.ages[i])}.A.{i:03d}.html"
            for i, b in enumerate(sc.boards)
        ]

    # 時間
    def utcnow(self) -> datetime:
        return self.sc.start + timedelta(seconds=self.mono - MONO0)

    def elapsed(self) -> float:
        return self.mono - MONO0

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.mono += seconds
        if self.elapsed() > 5 * 3600:
            raise RuntimeError("fake clock ran away: tool never stops")

    def login_count(self) -> int:
        return len(self.apis)

    # 推文資料
    def comments(self, i: int) -> list[tuple[str, str, str, datetime]]:
        push, boo = self.sc.history[i]
        base = self.sc.start - timedelta(seconds=1500)
        rows: list[tuple[str, str, str, datetime]] = []
        for k in range(push + boo):
            tag = "推" if k < push else "噓"
            when = base + timedelta(seconds=10 * k)
            rows.append((tag, f"sentuser{i}h{k % 5}", f"sentcontent-h-{i}-{k}", when))
        if i in self.sc.active:
            span = self.elapsed() - self.sc.onset - i * 0.5
            n = int(span // self.sc.interval) + 1 if span >= 0 else 0
            for j in range(n):
                when = self.sc.start + timedelta(
                    seconds=self.sc.onset + i * 0.5 + j * self.sc.interval
                )
                rows.append(("推", f"sentuser{i}x{j % 5}", f"sentcontent-{i}-{j}", when))
        return rows

    def index_of(self, key: str) -> int:
        return next(i for i, u in enumerate(self.urls) if key in u)

    def events_of(self, kind: str, idx: int | None = None) -> list[tuple[float, int, object]]:
        return [(t, i, x) for t, k, i, x in self.events if k == kind and (idx is None or i == idx)]


class FakeApi:
    def __init__(self, world: World, idx: int) -> None:
        self.world, self.idx, self.reads = world, idx, 0
        self.login_kwargs: dict[str, object] = {}
        self.logged_in = False

        def original_send(*_a: object, **_k: object) -> str:
            world.events.append((world.mono, "send", idx, None))
            return "screen"

        self.connect_core = SimpleNamespace(
            send=original_send,
            _RDQ=SimpleNamespace(get=lambda _n: self._screens()),
            get_screen_queue=lambda: self._screens()[-1:],
        )

    def _screens(self) -> list[str]:
        w = self.world
        if self.reads == 0:
            return list(w.sc.login_screens.get(self.idx, []))
        return list(w.sc.read_screens(self.idx, w)) if w.sc.read_screens else ["普通畫面"]

    def login(self, username: str, password: str, **kwargs: object) -> None:
        assert username == SECRET_ID and password == SECRET_PW
        self.login_kwargs = dict(kwargs)
        self.world.events.append((self.world.mono, "login", self.idx, dict(kwargs)))
        err = self.world.sc.login_errors.get(self.idx)
        if err is not None:
            raise err
        self.logged_in = True

    def logout(self) -> None:
        self.world.events.append((self.world.mono, "logout", self.idx, None))

    def get_post(self, board: str, aid: str | None = None, **_k: object) -> dict:
        w = self.world
        for _ in range(3):
            self.connect_core.send("key")
        w.events.append((w.mono, "get_post", self.idx, aid))
        if w.sc.read_error is not None:
            err = w.sc.read_error(self.idx, w)
            if err is not None:
                raise err
        self.reads += 1
        i = w.index_of(str(aid))
        return {
            "url": w.urls[i],
            "comments": [
                {
                    "time": _taipei_label(when),
                    "type": SimpleNamespace(name={"推": "PUSH", "噓": "BOO"}[tag]),
                    "author": user,
                    "content": content,
                    "ip": "192.0.2.1",
                }
                for tag, user, content, when in w.comments(i)
            ],
        }


def _fake_pyptt(world: World) -> SimpleNamespace:
    def make_api(**_kw: object) -> FakeApi:
        api = FakeApi(world, len(world.apis))
        world.apis.append(api)
        return api

    return SimpleNamespace(
        API=make_api,
        LogLevel=SimpleNamespace(SILENT=0),
        PostField=SimpleNamespace(url="url", comments="comments"),
        CommentField=SimpleNamespace(
            time="time", type="type", author="author", content="content", ip="ip"
        ),
        lib_util=SimpleNamespace(
            get_aid_from_url=lambda url: (
                url.split("/bbs/")[1].split("/")[0],
                url.split("/")[-1].removesuffix(".html"),
            )
        ),
    )


def _install(monkeypatch: pytest.MonkeyPatch, world: World) -> None:
    class FakeDT(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: ANN001, ANN206
            base = world.utcnow()
            moment = cls(*base.timetuple()[:6], base.microsecond, tzinfo=UTC)
            return moment.astimezone(tz) if tz else moment.replace(tzinfo=None)

    class FakePttClient:
        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def fetch(self, url: str) -> SimpleNamespace:
            world.events.append((world.mono, "web", world.index_of(url.split("/")[-1]), url))
            i = world.index_of(url.split("/")[-1])
            pushes = [
                (tag, user, content, _taipei_label(when))
                for tag, user, content, when in world.comments(i)
            ]
            return SimpleNamespace(status=200, html=_page(pushes))

    fake = _fake_pyptt(world)
    monkeypatch.setitem(sys.modules, "PyPtt", fake)
    fake_http = SimpleNamespace(get=lambda *_a, **_k: (_ for _ in ()).throw(OSError("blocked")))
    monkeypatch.setitem(sys.modules, "httpx2", fake_http)
    monkeypatch.setenv("PTT_BBS_USERNAME", SECRET_ID)
    monkeypatch.setenv("PTT_BBS_PASSWORD", SECRET_PW)
    monkeypatch.setattr(
        tool,
        "time",
        SimpleNamespace(
            monotonic=lambda: world.mono,
            sleep=world.sleep,
            time=lambda: world.utcnow().timestamp(),
        ),
    )
    monkeypatch.setattr(tool, "datetime", FakeDT)
    monkeypatch.setattr(tool, "PttClient", FakePttClient)
    monkeypatch.setattr(tool, "clock_offset_seconds", lambda *_a, **_k: 0.0)


def _write_p0(tmp_path: Path, boards: dict[str, bool] | None = None, passed: bool = True) -> Path:
    first = tmp_path / "first"
    first.mkdir(exist_ok=True)
    p0 = first / "p0.json"
    boards = boards or {"Gossiping": True, "Stock": True, "Tech_Job": True}
    p0.write_text(json.dumps({"p0": {"passed": passed, "boards_ok": boards}}), encoding="utf-8")
    return p0


def _seed_ledger(out: Path, entries: list[tuple[datetime, str]]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps({"at": at.isoformat(), "result": "ok", "conn": conn}) for at, conn in entries
    ]
    (out / "ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    sc: Scenario | None = None,
    *,
    extra: tuple[str, ...] = (),
    urls: list[str] | None = None,
    out: Path | None = None,
    p0: Path | None = None,
    seed: list[tuple[datetime, str]] | None = None,
    after_world: Callable[[World], None] | None = None,
) -> tuple[object, World, Path]:
    world = World(sc or Scenario())
    _install(monkeypatch, world)
    out = out or tmp_path / "retest"
    if seed:
        _seed_ledger(out, seed)
    p0 = p0 or _write_p0(tmp_path)
    argv = [
        "retest",
        "--url",
        *(urls or world.urls),
        "--out",
        str(out),
        "--p0",
        str(p0),
        *extra,
    ]
    try:
        code: object = tool.COMMANDS["retest"](tool.parse_args(argv))
    except SystemExit as exc:
        code = exc.code
    except tool.StopExperiment as stop:
        code = f"stop:{stop.reason}"
    return code, world, out


def _ledger(out: Path) -> list[dict]:
    path = out / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _run_dir(out: Path) -> Path:
    dirs = [p for p in out.iterdir() if p.is_dir()]
    assert len(dirs) == 1, dirs
    return dirs[0]


def _connections(out: Path) -> dict:
    return json.loads((_run_dir(out) / "connections.json").read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _login_times(world: World) -> list[float]:
    return [t for t, _i, _x in world.events_of("login")]


def _assert_refused(code: object, world: World, out: Path, seeded: int = 0) -> None:
    assert code == 3
    assert world.apis == []
    assert len(_ledger(out)) == seeded


# ---------- G-2 登入前檢查：不過就拒絕、不登入、不寫 ledger ----------


@pytest.mark.parametrize(
    "start",
    [
        datetime(2026, 11, 10, 11, 59, 59, tzinfo=UTC),  # 19:59:59 Taipei
        datetime(2026, 11, 10, 13, 45, 0, tzinfo=UTC),  # 21:45:00 Taipei
        datetime(2026, 11, 10, 3, 0, 0, tzinfo=UTC),  # 11:00 Taipei
    ],
)
def test_start_outside_evening_window_is_refused_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, start: datetime
) -> None:
    code, world, out = _run(monkeypatch, tmp_path, Scenario(start=start))
    _assert_refused(code, world, out)


@pytest.mark.parametrize(
    "start",
    [
        datetime(2026, 11, 10, 12, 0, 0, tzinfo=UTC),  # 20:00:00 Taipei
        datetime(2026, 11, 10, 13, 44, 59, tzinfo=UTC),  # 21:44:59 Taipei
    ],
)
def test_start_at_window_edges_is_accepted_and_reaches_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, start: datetime
) -> None:
    sc = Scenario(start=start, login_errors={0: LoginFailed("x")})
    _, world, _ = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 1


def test_duplicate_urls_are_refused_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    world = World(Scenario())
    urls = [world.urls[0], world.urls[1], world.urls[2], world.urls[0]]
    code, world, out = _run(monkeypatch, tmp_path, urls=urls)
    _assert_refused(code, world, out)


def test_url_count_other_than_four_is_rejected_by_the_parser() -> None:
    urls = [f"https://www.ptt.cc/bbs/Stock/M.1794310800.A.{i:03d}.html" for i in range(3)]
    with pytest.raises(SystemExit):
        tool.parse_args(["retest", "--url", *urls])


@pytest.mark.parametrize(
    "boards",
    [
        {"Gossiping": True, "Stock": True, "Tech_Job": False},
        {"Gossiping": True, "Stock": True},  # Tech_Job 不在 p0 裡
    ],
)
def test_board_not_proven_by_p0_is_refused_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, boards: dict[str, bool]
) -> None:
    code, world, out = _run(monkeypatch, tmp_path, p0=_write_p0(tmp_path, boards))
    _assert_refused(code, world, out)


def test_post_older_than_sixty_minutes_is_refused_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, world, out = _run(monkeypatch, tmp_path, Scenario(ages=(1800, 1800, 1800, 3601)))
    _assert_refused(code, world, out)


def test_post_exactly_sixty_minutes_old_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(ages=(1800, 1800, 1800, 3600), login_errors={0: LoginFailed("x")})
    _, world, _ = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 1


def test_web_score_below_thirty_is_refused_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, world, out = _run(
        monkeypatch, tmp_path, Scenario(history=((40, 0), (40, 0), (40, 0), (29, 0)))
    )
    _assert_refused(code, world, out)


def test_web_score_counts_boos_against_pushes_and_thirty_is_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    refused = Scenario(history=((40, 0), (40, 0), (40, 0), (40, 11)))  # 40 − 11 = 29
    code, world, out = _run(monkeypatch, tmp_path / "a", refused)
    _assert_refused(code, world, out)
    ok = Scenario(history=((40, 0), (40, 0), (40, 0), (40, 10)), login_errors={0: LoginFailed("x")})
    _, world2, _ = _run(monkeypatch, tmp_path / "b", ok)
    assert world2.login_count() == 1


def test_web_pages_are_fetched_once_each_before_the_first_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(login_errors={0: LoginFailed("x")})
    _, world, _ = _run(monkeypatch, tmp_path, sc)
    first_login = world.events_of("login")[0][0]
    pre = [i for t, i, _x in world.events_of("web") if t <= first_login]
    assert sorted(pre) == [0, 1, 2, 3]


def test_out_equal_to_first_experiment_directory_is_refused_and_untouched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    p0 = _write_p0(tmp_path)
    before = {p.name: p.read_bytes() for p in p0.parent.iterdir()}
    code, world, _ = _run(monkeypatch, tmp_path, out=p0.parent, p0=p0)
    assert code == 3
    assert world.apis == []
    assert {p.name: p.read_bytes() for p in p0.parent.iterdir()} == before


def test_normal_run_never_writes_into_the_first_experiment_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    p0 = _write_p0(tmp_path)
    before = {p.name: p.read_bytes() for p in p0.parent.iterdir()}
    _run(monkeypatch, tmp_path, Scenario(login_errors={0: LoginFailed("x")}), p0=p0)
    assert {p.name: p.read_bytes() for p in p0.parent.iterdir()} == before


def test_ledger_with_three_attempts_refuses_even_across_connections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed = [(START - timedelta(hours=h), c) for h, c in ((5, "A"), (4, "B"), (3, "C"))]
    code, world, out = _run(monkeypatch, tmp_path, seed=seed)
    _assert_refused(code, world, out, seeded=3)


def test_ledger_last_attempt_within_ten_minutes_refuses_before_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed = [(START - timedelta(minutes=9, seconds=30), "B")]
    code, world, out = _run(monkeypatch, tmp_path, seed=seed)
    _assert_refused(code, world, out, seeded=1)


@pytest.mark.parametrize("value", ["0", "4"])
def test_connections_outside_one_to_three_is_rejected_by_the_parser(value: str) -> None:
    urls = [f"https://www.ptt.cc/bbs/Stock/M.1794310800.A.{i:03d}.html" for i in range(4)]
    with pytest.raises(SystemExit):
        tool.parse_args(["retest", "--url", *urls, "--connections", value])


# ---------- G-2／G-3 完整流程：R2 長度、M 階段時間與證實 ----------


def test_full_run_opens_three_connections_with_ledger_conn_and_ten_minute_gaps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, world, out = _run(monkeypatch, tmp_path)
    assert code == 0
    assert [i for _t, i, _x in world.events_of("login")] == [0, 1, 2]
    for _t, _i, kwargs in world.events_of("login"):
        assert kwargs["kick_other_session"] is False
    times = _login_times(world)
    assert times[1] - times[0] >= 600 and times[2] - times[1] >= 600
    rows = _ledger(out)
    assert [r["conn"] for r in rows] == ["A", "B", "C"]
    assert all(r["result"] != "attempt" for r in rows)
    assert set(rows[0]) <= {"at", "result", "conn"}
    stamps = [datetime.fromisoformat(r["at"]) for r in rows]
    assert all(b - a >= timedelta(minutes=10) for a, b in zip(stamps, stamps[1:], strict=False))
    assert SECRET_ID not in json.dumps(rows) and SECRET_PW not in json.dumps(rows)
    assert (out / "ledger.jsonl").exists()  # 在 --out 底下，不在第一次的目錄


def test_r2_lasts_at_least_forty_minutes_even_when_samples_arrive_early(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, world, _ = _run(monkeypatch, tmp_path)
    t_a, t_b = _login_times(world)[:2]
    assert 2400 <= t_b - t_a <= 2400 + 400
    assert not [t for t, _i, _x in world.events_of("get_post", 1) if t < t_a + 2400]


def test_r2_ends_early_when_samples_reach_target_after_forty_minutes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(onset=2700)  # 新推文 45 分鐘後才開始出現，約 49 分鐘湊滿 100 則
    _, world, _ = _run(monkeypatch, tmp_path, sc)
    t_a, t_b = _login_times(world)[:2]
    assert 2700 < t_b - t_a < 3300


def test_r2_runs_to_sixty_minutes_and_skips_b_c_when_samples_are_short(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(interval=600.0)
    _, world, out = _run(monkeypatch, tmp_path, sc)
    t_a = _login_times(world)[0]
    t_out = world.events_of("logout", 0)[0][0]
    assert 3600 <= t_out - t_a <= 3600 + 300
    assert world.login_count() == 1  # D-051：保留登入額度給重跑
    assert len(_ledger(out)) == 1
    assert [r["conn"] for r in _ledger(out)] == ["A"]


def test_r2_does_not_end_early_when_samples_come_from_fewer_than_three_posts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(active=(0, 1), interval=5.0)  # 100 則很快湊滿，但只有 2 篇有新推文
    _, world, _ = _run(monkeypatch, tmp_path, sc)
    t_a = _login_times(world)[0]
    t_out = world.events_of("logout", 0)[0][0]
    assert t_out - t_a >= 3600
    assert world.login_count() == 1


def test_r2_stop_condition_logs_out_a_and_never_opens_other_connections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(
        read_error=lambda i, w: ConnectionClosed("x") if w.elapsed() > 900 and i == 0 else None
    )
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 1
    assert len(world.events_of("logout", 0)) == 1
    stop_t = world.events_of("logout", 0)[0][0]
    assert not [t for t, _i, _x in world.events_of("get_post") if t > stop_t]
    assert len(_ledger(out)) == 1


def test_m_stage_timing_reads_and_logout_of_all_connections(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, world, out = _run(monkeypatch, tmp_path)
    t_a, t_b, t_c = _login_times(world)
    assert 600 <= t_c - t_b <= 600 + 200
    b_reads = [t for t, _i, _x in world.events_of("get_post", 1)]
    assert len([t for t in b_reads if t < t_c]) >= 3
    assert all(b - a >= 60 - 1e-6 for a, b in zip(b_reads, b_reads[1:], strict=False))
    a_reads = [t for t, _i, _x in world.events_of("get_post", 0)]
    assert any(t_b < t < t_c for t in a_reads)  # A 在 M 階段繼續輪讀
    assert all(b - a >= 20 - 1e-6 for a, b in zip(a_reads, a_reads[1:], strict=False))
    for idx in (0, 1, 2):
        assert len(world.events_of("logout", idx)) == 1
        assert any(t > t_c for t, _i, _x in world.events_of("get_post", idx))
    last_logout = max(t for t, _i, _x in world.events_of("logout"))
    assert last_logout - t_b <= 900
    assert not [t for t, _i, _x in world.events_of("get_post") if t > last_logout]
    conn = _connections(out)
    assert conn["proven"] == 3 and conn["tested"] == 3


def test_every_connection_throttles_its_own_sends_to_one_second(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, world, _ = _run(monkeypatch, tmp_path)
    for idx in (0, 1, 2):
        sends = [t for t, _i, _x in world.events_of("send", idx)]
        assert sends
        assert all(b - a >= 1 - 1e-6 for a, b in zip(sends, sends[1:], strict=False))


def test_m_events_are_recorded_as_phase_m_and_phases_are_known(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, _, out = _run(monkeypatch, tmp_path)
    run_dir = _run_dir(out)
    assert run_dir.name == RUN_ID
    events = _jsonl(run_dir / "events.jsonl")
    reads = _jsonl(run_dir / "reads.jsonl")
    assert {e["phase"] for e in events} <= {"r2", "m", "web"}
    assert {r["phase"] for r in reads} == {"r2", "m"}
    assert any(e["phase"] == "m" for e in events)
    assert any(e["phase"] == "r2" for e in events)


@pytest.mark.parametrize(("connections", "logins"), [(1, 1), (2, 2), (3, 3)])
def test_connections_option_limits_how_many_connections_are_tested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, connections: int, logins: int
) -> None:
    _, world, out = _run(monkeypatch, tmp_path, extra=("--connections", str(connections)))
    assert world.login_count() == logins
    assert len(_ledger(out)) == logins
    assert _connections(out)["proven"] == logins


def test_remaining_ledger_quota_caps_connections_below_the_option(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed = [(START - timedelta(hours=2), "A")]
    _, world, out = _run(monkeypatch, tmp_path, seed=seed)
    assert world.login_count() == 2
    assert len(_ledger(out)) == 3
    assert _connections(out)["proven"] == 2


def test_only_one_quota_left_runs_r2_without_m_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    seed = [(START - timedelta(hours=3), "A"), (START - timedelta(hours=2), "B")]
    _, world, out = _run(monkeypatch, tmp_path, seed=seed)
    assert world.login_count() == 1
    assert len(_ledger(out)) == 3
    assert _connections(out)["proven"] == 1


# ---------- G-3 / G-3a M 階段的立即停止 ----------


def _assert_all_open_connections_logged_out_once(world: World) -> None:
    for api in world.apis:
        if api.logged_in:
            assert len(world.events_of("logout", api.idx)) == 1


def test_b_login_failure_stops_without_logout_or_keys_for_b(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(login_errors={1: LoginFailed(f"{SECRET_ID} {SECRET_PW}")})
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 2
    assert world.events_of("logout", 1) == []
    assert world.events_of("send", 1) == []
    assert world.events_of("get_post", 1) == []
    assert len(world.events_of("logout", 0)) == 1
    rows = _ledger(out)
    assert [r["conn"] for r in rows] == ["A", "B"]
    assert rows[1]["result"] != "attempt" and "fail" in rows[1]["result"].lower()
    conn = _connections(out)
    assert conn["proven"] == 1 and conn["stop_reason"]
    assert SECRET_PW not in json.dumps(rows) and SECRET_ID not in json.dumps(rows)


def test_c_login_failure_keeps_k_at_two_and_logs_out_a_and_b_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(login_errors={2: LoginFailed("refused")})
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 3
    assert world.events_of("logout", 2) == []
    assert world.events_of("send", 2) == []
    assert len(world.events_of("logout", 0)) == 1 and len(world.events_of("logout", 1)) == 1
    conn = _connections(out)
    assert conn["proven"] == 2 and conn["stop_reason"]
    assert len(_ledger(out)) == 3  # 失敗的也算一次


def test_old_connection_failing_after_b_opens_stops_with_kicked_or_closed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(
        read_error=lambda i, w: ConnectionClosed("x") if i == 0 and w.login_count() >= 2 else None
    )
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 2
    conn = _connections(out)
    assert conn["proven"] == 1
    assert "kicked_or_closed" in str(conn["stop_reason"])
    _assert_all_open_connections_logged_out_once(world)


def test_old_connection_failing_after_c_opens_keeps_two_proven(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(
        read_error=lambda i, w: ConnectionClosed("x") if i == 0 and w.login_count() >= 3 else None
    )
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 3
    conn = _connections(out)
    assert conn["proven"] == 2
    assert "kicked_or_closed" in str(conn["stop_reason"])
    _assert_all_open_connections_logged_out_once(world)


def test_b_read_failure_after_b_opens_stops_and_never_opens_c(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(read_error=lambda i, w: ConnectionClosed("x") if i == 1 else None)
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 2
    assert _connections(out)["proven"] == 1
    _assert_all_open_connections_logged_out_once(world)


def test_multi_login_text_on_an_already_open_connection_stops(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(
        read_screens=lambda i, w: (
            ["注意: 您有其它連線已登入此帳號。"]
            if i == 0 and w.login_count() >= 2
            else ["普通畫面"]
        )
    )
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 2
    conn = _connections(out)
    assert conn["proven"] == 1 and conn["stop_reason"]
    _assert_all_open_connections_logged_out_once(world)


@pytest.mark.parametrize("text", ["您想刪除其他重複登入的連線嗎", "您有其他連線已登入"])
def test_multi_login_text_on_the_new_connections_own_login_screen_is_ignored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, text: str
) -> None:
    sc = Scenario(login_screens={1: [text], 2: [text]})
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 3
    assert _connections(out)["proven"] == 3


def test_other_stop_keywords_still_stop_during_m_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sc = Scenario(
        read_screens=lambda i, w: ["系統過載，請稍後再試"] if i == 1 else ["普通畫面"],
    )
    _, world, out = _run(monkeypatch, tmp_path, sc)
    assert world.login_count() == 2
    assert _connections(out)["stop_reason"]
    _assert_all_open_connections_logged_out_once(world)


def test_multi_login_keywords_are_a_separate_group_not_in_the_general_stop_list() -> None:
    assert {"重複登入", "其它連線已登入", "其他連線已登入"} <= set(tool._MULTI_LOGIN_KEYWORDS)
    for text in ("注意: 您有其它連線已登入此帳號。", "您想刪除其他重複登入的連線嗎？[Y/n]"):
        tool.check_screens([text])  # 不丟例外：登入時這是正常畫面


# ---------- G-4 工具修正 ----------


def test_leak_scan_skips_ledger_even_if_it_contains_the_secret(tmp_path: Path) -> None:
    (tmp_path / "ledger.jsonl").write_text(f'{{"result": "{SECRET_ID}"}}\n', encoding="utf-8")
    (tmp_path / "notes.json").write_text("clean", encoding="utf-8")
    assert tool.finish_output_check(tmp_path, SECRET_ID, SECRET_PW) == 0
    assert (tmp_path / "ledger.jsonl").exists()
    assert tool.scan_and_purge(tmp_path, [SECRET_ID, SECRET_PW]) == []


def test_leak_scan_skips_ledger_in_a_nested_run_directory(tmp_path: Path) -> None:
    nested = tmp_path / "run"
    nested.mkdir()
    (nested / "ledger.jsonl").write_text(SECRET_PW, encoding="utf-8")
    assert tool.finish_output_check(tmp_path, SECRET_ID, SECRET_PW) == 0


def test_short_username_inside_a_hash_key_is_not_a_leak(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text('{"key": "0123abc456789def"}\n', encoding="utf-8")
    assert tool.finish_output_check(tmp_path, "abc", SECRET_PW) == 0
    assert events.exists()


def test_short_username_standing_alone_is_still_a_leak(tmp_path: Path) -> None:
    leaked = tmp_path / "events.jsonl"
    leaked.write_text('{"user": "abc"}\n', encoding="utf-8")
    assert tool.finish_output_check(tmp_path, "abc", SECRET_PW) == 2
    assert not leaked.exists()


@pytest.mark.parametrize("body", ["abc", "abc\nnext", "x abc", "user=abc;", "id:abc,"])
def test_secret_with_non_alphanumeric_neighbours_or_file_edges_is_a_leak(
    tmp_path: Path, body: str
) -> None:
    leaked = tmp_path / "events.jsonl"
    leaked.write_text(body, encoding="utf-8")
    assert tool.scan_and_purge(tmp_path, ["abc"]) == [leaked]
    assert not leaked.exists()


@pytest.mark.parametrize("body", ["abcd", "xabc", "1abc", "abc9", "zzabczz"])
def test_secret_glued_to_letters_or_digits_is_not_a_leak(tmp_path: Path, body: str) -> None:
    kept = tmp_path / "events.jsonl"
    kept.write_text(body, encoding="utf-8")
    assert tool.scan_and_purge(tmp_path, ["abc"]) == []
    assert kept.exists()


def test_password_leak_with_special_characters_is_still_found(tmp_path: Path) -> None:
    leaked = tmp_path / "events.jsonl"
    leaked.write_text(f"pw={SECRET_PW}\n", encoding="utf-8")
    assert tool.finish_output_check(tmp_path, SECRET_ID, SECRET_PW) == 2
    assert not leaked.exists()


def test_pyptt_logger_keeps_only_null_handler_and_does_not_propagate() -> None:
    logger = logging.getLogger("PyPtt")
    saved = (list(logger.handlers), logger.propagate)

    def make_api(**_k: object) -> SimpleNamespace:
        logger.addHandler(logging.StreamHandler())  # 模擬 PyPtt 建 API 時掛的 console handler
        return SimpleNamespace(
            connect_core=SimpleNamespace(send=lambda *_a, **_k: None, get_screen_queue=lambda: []),
            login=lambda *_a, **_k: None,
            logout=lambda: None,
        )

    ptt = SimpleNamespace(API=make_api, LogLevel=SimpleNamespace(SILENT=0))
    try:
        tool.open_session(ptt, SECRET_ID, tool.SecretStr(SECRET_PW), lambda: 0.0, lambda _s: None)
        assert logger.handlers
        assert all(type(h) is logging.NullHandler for h in logger.handlers)
        assert logger.propagate is False
    finally:
        logger.handlers[:] = saved[0]
        logger.propagate = saved[1]


_URLS4 = [f"https://www.ptt.cc/bbs/Stock/M.1794310800.A.{i:03d}.html" for i in range(4)]
_SUBCOMMANDS: dict[str, list[str]] = {
    "probe": ["--url", _URLS4[0]],
    "run": ["--url", *_URLS4[:3]],
    "summarize": ["--run-id", "r", "--hot-concurrent-p90", "33"],
    "retest": ["--url", *_URLS4],
    "summarize-retest": ["--run-id", "r", "--hot-concurrent-p90", "33"],
}


@pytest.mark.parametrize("sub", list(_SUBCOMMANDS))
def test_out_option_is_accepted_before_and_after_every_subcommand(sub: str) -> None:
    before = tool.parse_args(["--out", "X", sub, *_SUBCOMMANDS[sub]])
    after = tool.parse_args([sub, *_SUBCOMMANDS[sub], "--out", "X"])
    assert before.out == "X" and after.out == "X"


@pytest.mark.parametrize(
    ("sub", "default"),
    [
        ("probe", "data/spike/bbs"),
        ("run", "data/spike/bbs"),
        ("summarize", "data/spike/bbs"),
        ("retest", "data/spike/bbs-retest"),
        ("summarize-retest", "data/spike/bbs-retest"),
    ],
)
def test_default_out_directory_per_subcommand(sub: str, default: str) -> None:
    assert tool.parse_args([sub, *_SUBCOMMANDS[sub]]).out == default


def test_retest_option_defaults_match_the_spec() -> None:
    args = tool.parse_args(["retest", "--url", *_URLS4])
    assert args.connections == 3
    assert args.p0 == "data/spike/bbs/p0.json"
    assert len(args.url) == 4
    summ = tool.parse_args(["summarize-retest", "--run-id", "r", "--hot-concurrent-p90", "33"])
    assert summ.rules == "unconfirmed" and summ.hot_concurrent_p90 == 33


def _subparser_help(
    sub: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> dict[str, str]:
    monkeypatch.setenv("COLUMNS", "200")
    with pytest.raises(SystemExit):
        tool.parse_args([sub, "--help"])
    helps: dict[str, str] = {}
    current: str | None = None
    for line in capsys.readouterr().out.splitlines():
        match = re.match(r"^  (-\S+)(.*)$", line)
        if match:
            current = match.group(1)
            parts = re.split(r"\s{2,}", match.group(2).strip(), maxsplit=1)
            helps[current] = parts[1] if len(parts) > 1 else ""
        elif current and line.startswith("      ") and line.strip():
            helps[current] += " " + line.strip()
        else:
            current = None
    return {k: v for k, v in helps.items() if k not in ("-h", "--help")}


@pytest.mark.parametrize("sub", list(_SUBCOMMANDS))
def test_every_option_has_help_text(
    sub: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    helps = _subparser_help(sub, monkeypatch, capsys)
    assert "--out" in helps
    assert all(text.strip() for text in helps.values()), helps


def test_time_options_help_state_unit_and_default(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    run = _subparser_help("run", monkeypatch, capsys)
    for opt, default in (("--p1-minutes", "10"), ("--p2-minutes", "30"), ("--tail-minutes", "20")):
        assert "分鐘" in run[opt] and default in run[opt], (opt, run[opt])
    retest = _subparser_help("retest", monkeypatch, capsys)
    assert "3" in retest["--connections"]
    assert "data/spike/bbs/p0.json" in retest["--p0"]
    assert "data/spike/bbs-retest" in retest["--out"]
    summ = _subparser_help("summarize-retest", monkeypatch, capsys)
    assert "p90" in summ["--hot-concurrent-p90"] or "同時" in summ["--hot-concurrent-p90"]
    assert "unconfirmed" in summ["--rules"]


# ---------- 手寫的一次實驗資料：summarize／summarize-retest ----------


def _post_id(i: int, age_seconds: float, start: datetime = START) -> str:
    epoch = int(start.timestamp() - age_seconds)
    return tool.post_id_from_url(f"https://www.ptt.cc/bbs/Stock/M.{epoch}.A.{i:03d}.html")


def _events(
    post: str,
    phase: str,
    n: int,
    *,
    u: float = 80.0,
    step: float = 20.0,
    first: datetime = START + timedelta(minutes=1),
    prefix: str = "k",
) -> list[dict]:
    rows = []
    for k in range(n):
        minute = first + timedelta(seconds=step * k)
        rows.append(
            {
                "phase": phase,
                "key": f"{prefix}-{post}-{k}",
                "u": u,
                "l": max(0.0, u - 60),
                "e": u - 30,
                "t": (minute + timedelta(seconds=u)).isoformat(),
                "post": post,
            }
        )
    return rows


def _reads(phase: str, n: int, seconds: float, sends: int, screens: int) -> list[dict]:
    return [
        {
            "phase": phase,
            "post": "p",
            "ok": True,
            "seconds": seconds,
            "sends": sends,
            "screens": screens,
            "comments": 3,
            "time_unparsed": 0,
            "at": START.isoformat(),
        }
        for _ in range(n)
    ]


def _write_run(
    out: Path,
    posts: list[str],
    events: list[dict],
    reads: list[dict],
    *,
    stop: dict | None = None,
    connections: dict | None = None,
) -> Path:
    run_dir = out / RUN_ID
    run_dir.mkdir(parents=True)
    (out / "p0.json").write_text(
        json.dumps({"p0": {"passed": True, "boards_ok": {"Stock": True}}}), encoding="utf-8"
    )
    (run_dir / "meta.json").write_text(json.dumps({"run_id": RUN_ID, "posts": posts}))
    (run_dir / "clock.json").write_text(json.dumps({"offset_seconds": 0.1}))
    (run_dir / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))
    (run_dir / "reads.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reads))
    if stop is not None:
        (run_dir / "stop.json").write_text(json.dumps(stop))
    if connections is not None:
        (run_dir / "connections.json").write_text(json.dumps(connections))
    return run_dir


def _summarize(out: Path, sub: str = "summarize", *extra: str) -> dict:
    args = tool.parse_args(
        ["--out", str(out), sub, "--run-id", RUN_ID, "--hot-concurrent-p90", "33", *extra]
    )
    assert tool.COMMANDS[sub](args) == 0
    return json.loads((out / RUN_ID / "summary.json").read_text(encoding="utf-8"))


def test_summarize_judges_only_qualifying_posts_and_lists_the_rest_as_excluded(
    tmp_path: Path,
) -> None:
    old = _post_id(0, 7200)  # 發文 2 小時前：年齡不合
    cold = _post_id(1, 1800)  # 年輕但任一 10 分鐘內都不到 10 則
    boundary = _post_id(2, 3600)  # 剛好 60 分鐘：合格
    young = _post_id(3, 600)
    events = (
        _events(old, "p2", 120, u=40.0)
        + _events(cold, "p2", 5, u=40.0, step=1200.0)
        + _events(boundary, "p2", 30, u=130.0)
        + _events(young, "p2", 30, u=130.0)
    )
    _write_run(tmp_path, [old, cold, boundary, young], events, _reads("p2", 4, 7.0, 5, 3))
    summary = _summarize(tmp_path)
    assert summary["p2"]["samples"] == 60
    assert summary["p2"]["posts"] == 2
    assert summary["p2"]["p50_e"] == 100.0
    assert {x["post_id"] for x in summary["excluded"]} == {old, cold}
    assert all(x["reason"] for x in summary["excluded"])
    assert (
        summary["excluded"][0]["reason"] != ""
        and len({x["reason"] for x in summary["excluded"]}) == 2
    )
    assert summary["decision"]["recommend"] is False
    assert summary["decision"]["latency"] is False


def test_hot_check_unions_bbs_and_web_keys_by_labelled_minute(tmp_path: Path) -> None:
    post = _post_id(1, 1800)
    bbs = _events(post, "p2", 4, step=60.0, prefix="b")  # 單獨只有 4 則
    web = _events(post, "web", 8, step=60.0, prefix="w")  # 聯集 12 則，同在 10 分鐘內
    others = [e for i in (2, 3, 4) for e in _events(_post_id(i, 1800), "p2", 30, u=80.0)]
    posts = [post, *{e["post"] for e in others}]
    _write_run(tmp_path, posts, bbs + web + others, _reads("p2", 2, 7.0, 5, 3))
    summary = _summarize(tmp_path)
    assert post not in {x["post_id"] for x in summary["excluded"]}
    assert summary["p2"]["samples"] == 4 + 90


def test_summarize_capacity_uses_only_judged_phase_reads_and_capacity_all_uses_all(
    tmp_path: Path,
) -> None:
    posts = [_post_id(i, 1800) for i in range(3)]
    events = [e for p in posts for e in _events(p, "p2", 40)]
    reads = _reads("p1", 4, 100.0, 50, 9) + _reads("p2", 4, 10.0, 5, 3)
    _write_run(tmp_path, posts, events, reads)
    summary = _summarize(tmp_path)
    cap, all_ = summary["capacity"], summary["capacity_all"]
    assert cap["avg_read_seconds"] == 10.0
    assert cap["avg_sends"] == 5.0 and cap["avg_screens"] == 3.0
    assert cap["n_max"] == 3 and cap["connections_needed"] == 11
    assert all_["avg_read_seconds"] == 55.0
    assert all_["avg_sends"] == 27.5 and all_["avg_screens"] == 6.0


# ---------- summarize-retest：G-5 判定與欄位 ----------


def _good_retest(
    tmp_path: Path,
    *,
    counts: tuple[int, ...] = (30, 30, 30, 30),
    u: float = 80.0,
    posts_in_meta: int = 4,
    m_events: int = 0,
    stop: dict | None = None,
    connections: dict | None = None,
) -> Path:
    posts = [_post_id(i, 1800) for i in range(4)]
    events = [e for p, n in zip(posts, counts, strict=True) for e in _events(p, "r2", n, u=u)]
    if m_events:
        events += _events(posts[0], "m", m_events, first=START + timedelta(hours=1), prefix="m")
    reads = _reads("r2", 8, 7.1, 5, 3) + _reads("m", 3, 30.0, 15, 7)
    conn = connections or {"tested": 3, "proven": 3, "stop_reason": None}
    return _write_run(tmp_path, posts[:posts_in_meta], events, reads, stop=stop, connections=conn)


def test_retest_recommends_when_all_three_criteria_hold(tmp_path: Path) -> None:
    _good_retest(tmp_path)
    summary = _summarize(tmp_path, "summarize-retest")
    assert summary["decision"]["recommend"] is True
    assert summary["excluded"] == []
    assert summary["connections"]["proven"] == 3


@pytest.mark.parametrize(
    ("kwargs", "why"),
    [
        ({"counts": (25, 25, 25, 24)}, "99 則不到 100"),
        ({"counts": (60, 60, 0, 0)}, "樣本只來自 2 篇"),
        ({"u": 91.0}, "p50(E)=61 > 60"),
        ({"counts": (40, 40, 40, 0), "posts_in_meta": 3}, "輪讀篇數不是 4"),
        ({"stop": {"reason": "ConnectionClosed"}}, "R2 觸發立即停止"),
        ({"m_events": 30, "counts": (25, 25, 25, 24)}, "M 階段的事件不算樣本"),
    ],
)
def test_retest_does_not_recommend_when_a_criterion_fails(
    tmp_path: Path, kwargs: dict, why: str
) -> None:
    _good_retest(tmp_path, **kwargs)
    summary = _summarize(tmp_path, "summarize-retest")
    assert summary["decision"]["recommend"] is False, why


def test_retest_p50_exactly_sixty_is_accepted(tmp_path: Path) -> None:
    _good_retest(tmp_path, u=90.0)
    assert _summarize(tmp_path, "summarize-retest")["decision"]["recommend"] is True


def test_retest_m_stage_stop_keeps_r3_true_and_degrades_k(tmp_path: Path) -> None:
    conn = {"tested": 3, "proven": 2, "stop_reason": "kicked_or_closed"}
    _good_retest(tmp_path, connections=conn)
    summary = _summarize(tmp_path, "summarize-retest")
    assert summary["decision"]["recommend"] is True
    assert summary["connections"]["proven"] == 2
    assert summary["connections"]["tested"] == 3
    assert summary["connections"]["stop_reason"] == "kicked_or_closed"


def test_retest_reports_n_max_connections_needed_and_coverage(tmp_path: Path) -> None:
    conn = {"tested": 3, "proven": 2, "stop_reason": "kicked_or_closed"}
    _good_retest(tmp_path, connections=conn)
    summary = _summarize(tmp_path, "summarize-retest")
    cap = summary["capacity"]
    assert cap["avg_read_seconds"] == pytest.approx(7.1)  # 只用 r2
    assert cap["n_max"] == 4 and cap["connections_needed"] == 9
    assert summary["capacity_all"]["avg_read_seconds"] == pytest.approx((8 * 7.1 + 3 * 30) / 11)
    assert cap["avg_sends"] == 5.0 and cap["avg_screens"] == 3.0
    flat = json.dumps(summary)
    assert any(abs(v - 8 / 33) < 1e-3 for v in _numbers(summary)), flat  # 4 × k 占 p90


def _numbers(node: object) -> list[float]:
    if isinstance(node, bool):
        return []
    if isinstance(node, int | float):
        return [float(node)]
    if isinstance(node, dict):
        return [n for v in node.values() for n in _numbers(v)]
    if isinstance(node, list):
        return [n for v in node for n in _numbers(v)]
    return []


def test_retest_excludes_non_qualifying_posts_from_the_judgement(tmp_path: Path) -> None:
    posts = [_post_id(i, 1800) for i in range(3)] + [_post_id(3, 7200)]
    events = [e for p in posts[:3] for e in _events(p, "r2", 30, u=91.0)]
    events += _events(posts[3], "r2", 60, u=40.0)  # 太老，若被算進來 p50(E) 會變小
    conn = {"tested": 1, "proven": 1, "stop_reason": None}
    _write_run(tmp_path, posts, events, _reads("r2", 8, 7.1, 5, 3), connections=conn)
    summary = _summarize(tmp_path, "summarize-retest")
    assert [x["post_id"] for x in summary["excluded"]] == [posts[3]]
    assert summary["r2"]["samples"] == 90
    assert summary["r2"]["p50_e"] == 61.0
    assert summary["decision"]["recommend"] is False


# ---------- 完整流程後的輸出不含秘密、使用者 ID、推文 ----------


def test_outputs_and_summary_hold_no_credentials_user_ids_or_comment_text(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    code, world, out = _run(monkeypatch, tmp_path)
    assert code == 0
    args = tool.parse_args(
        ["summarize-retest", "--out", str(out), "--run-id", RUN_ID, "--hot-concurrent-p90", "33"]
    )
    assert tool.COMMANDS["summarize-retest"](args) == 0
    run_dir = out / RUN_ID
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    for key in ("decision", "connections", "excluded", "capacity", "capacity_all"):
        assert key in summary
    assert summary["connections"]["proven"] == 3
    for path in out.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in (SECRET_ID, SECRET_PW, "sentuser", "sentcontent"):
                assert needle not in text, (path.name, needle)

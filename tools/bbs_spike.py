"""PTT BBS 延遲實驗（一次性，由甲方手動執行，開發規格 7.31）。全程唯讀，不進測試與 CI。

用法（帳密只讀環境變數 PTT_BBS_USERNAME、PTT_BBS_PASSWORD）：
  uv run --group bbs-spike --env-file .env python tools/bbs_spike.py probe --url <各看板一篇>...
  uv run --group bbs-spike --env-file .env python tools/bbs_spike.py run --url <熱門文章 3 篇>
  uv run python tools/bbs_spike.py summarize --run-id <id> --hot-concurrent-p90 <n>
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import sys
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from types import ModuleType
from typing import Any
from urllib.parse import urlparse

from pydantic import SecretStr

from radar.collector.http import OVER18_COOKIE, USER_AGENT, PttClient
from radar.collector.parsers.ptt import ParseError, parse_post_page, post_id_from_url
from radar.collector.parsers.ptt_time import created_at_from_filename, parse_comment_time
from radar.common.enums import CommentType
from radar.common.ids import split_post_id
from radar.common.log import log, setup_logging
from radar.common.rate_limit import RateLimiter

__all__ = ["SecretStr"]

# ---------- 上限（開發規格 7.31 B）：程式常數，放寬要改程式、經 PR ----------
MAX_LOGINS = 3
MIN_LOGIN_INTERVAL_SECONDS = 600
MIN_READ_INTERVAL_SECONDS = 20
READ_JITTER_MAX_SECONDS = 5
MIN_SEND_INTERVAL_SECONDS = 1
WEB_POLL_INTERVAL_SECONDS = 60
MAX_CONSECUTIVE_READ_FAILURES = 3
P0_MAX_SECONDS_PER_POST = 120
P0_MAX_SENDS_PER_POST = 120

# ---------- 判定門檻（7.31 C） ----------
P1_MIN_SAMPLES = 30
P2_MIN_SAMPLES = 100
P2_MIN_POSTS = 2
MAX_UNMATCHED_RATIO = 0.1
P50_E_LIMIT_SECONDS = 60
CLOCK_SKEW_LIMIT_SECONDS = 5
_CYCLE_BUDGET_SECONDS = 120
_AVG_WAIT_SECONDS = MIN_READ_INTERVAL_SECONDS + READ_JITTER_MAX_SECONDS / 2

_USERNAME_VAR = "PTT_BBS_USERNAME"
_PASSWORD_VAR = "PTT_BBS_PASSWORD"
_STOP_EXCEPTIONS = frozenset(
    {"UseTooManyResources", "LoginTooOften", "UserHasPreviouslyBeenBanned", "WrongIDorPassword"}
)
_STOP_KEYWORDS = ("登入太頻繁", "系統過載")
_READ_FAILURE_EXCEPTIONS = frozenset({"NoSuchPost", "NoSuchBoard", "NoPermission"})
_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[@-Z\\-_])")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_TYPE_SYMBOLS = {"PUSH": "推", "BOO": "噓", "ARROW": "→"}
_DEFAULT_OUT = "data/spike/bbs"


# ---------- 例外 ----------


class LoginRefused(Exception):
    """登入次數或間隔超過上限；沒有送出任何登入。"""


class StopExperiment(Exception):
    """立即停止條件成立；呼叫端登出、不重試。"""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class BbsLoginError(StopExperiment):
    """只帶例外類別名稱；原例外（可能含帳密）不保留。"""


class P0NotPassed(Exception):
    """P0 探測沒過或沒做，拒絕跑 P1、P2。"""


# ---------- 秘密保護 ----------


def sanitize_screen(raw: str) -> str:
    """去掉 ANSI 與控制字元（保留換行），畫面內容才能安全寫檔。"""
    return _CONTROL_RE.sub("", _ANSI_RE.sub("", raw.replace("\r", "")))


def scan_and_purge(root: Path, secrets: Iterable[str]) -> list[Path]:
    return [path for path, _ in _find_leaks(root, {s: s for s in secrets})]


def _find_leaks(root: Path, secrets: Mapping[str, str]) -> list[tuple[Path, list[str]]]:
    """secrets 為 值 → 名稱；含值的檔案刪除，回傳（路徑, 名稱）。空值不比對。"""
    leaks: list[tuple[Path, list[str]]] = []
    if not root.exists():
        return leaks
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        data = path.read_bytes()
        names = [name for value, name in secrets.items() if value and value.encode() in data]
        if names:
            path.unlink()
            leaks.append((path, names))
    return leaks


def finish_output_check(root: Path, username: str, password: str) -> int:
    """掃輸出目錄；有洩漏就刪檔、非 0 結束，只印變數名稱。"""
    secrets = {username: _USERNAME_VAR, password: _PASSWORD_VAR}
    leaks = _find_leaks(root, secrets)
    if not leaks:
        return 0
    names = sorted({n for _, names in leaks for n in names})
    _say(f"LEAK: {', '.join(names)} found in {len(leaks)} output file(s); files deleted")
    return 2


def _say(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ---------- 登入次數與間隔 ----------


class Ledger:
    """每次登入嘗試一行 JSON；跨執行累計，超過上限直接拒絕。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    def record(self, at: datetime, result: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": at.isoformat(), "result": result}) + "\n")

    def attempts(self) -> list[datetime]:
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return [datetime.fromisoformat(json.loads(ln)["at"]) for ln in lines if ln.strip()]


def check_login_allowed(attempts: Sequence[datetime], now: datetime) -> None:
    if len(attempts) >= MAX_LOGINS:
        raise LoginRefused(f"login attempts reached the limit ({MAX_LOGINS})")
    if attempts and now - max(attempts) < timedelta(seconds=MIN_LOGIN_INTERVAL_SECONDS):
        raise LoginRefused(f"wait at least {MIN_LOGIN_INTERVAL_SECONDS}s after the last login")


# ---------- 讀取與 send 節流 ----------


class ReadPacer:
    def __init__(
        self,
        now: Callable[[], float],
        sleep: Callable[[float], None],
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._now = now
        self._sleep = sleep
        self._uniform = uniform
        self._last_done: float | None = None

    def mark_done(self) -> None:
        self._last_done = self._now()

    def wait(self) -> None:
        if self._last_done is None:
            return
        target = MIN_READ_INTERVAL_SECONDS + self._uniform(0, READ_JITTER_MAX_SECONDS)
        remaining = target - (self._now() - self._last_done)
        if remaining > 0:
            self._sleep(remaining)


class SendThrottle:
    """包住 connect_core.send：間隔 ≥ 1 秒並計數。"""

    def __init__(
        self,
        wrapped: Callable[..., Any],
        now: Callable[[], float],
        sleep: Callable[[float], None],
    ) -> None:
        self._wrapped = wrapped
        self._now = now
        self._sleep = sleep
        self._last: float | None = None
        self.count = 0

    def __call__(self, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401 - 透傳第三方呼叫
        if self._last is not None:
            gap = self._now() - self._last
            if gap < MIN_SEND_INTERVAL_SECONDS:
                self._sleep(MIN_SEND_INTERVAL_SECONDS - gap)
        self._last = self._now()
        self.count += 1
        return self._wrapped(*args, **kwargs)


def install_send_throttle(
    api: Any, now: Callable[[], float], sleep: Callable[[float], None]
) -> SendThrottle:
    throttle = SendThrottle(api.connect_core.send, now, sleep)
    api.connect_core.send = throttle
    return throttle


def open_session(
    ptt: ModuleType | Any,
    username: str,
    password: SecretStr,
    now: Callable[[], float],
    sleep: Callable[[float], None],
) -> Any:  # noqa: ANN401 - PyPtt.API 無型別
    """登入一次、不重試；send 包裝在登入之後，包裝層碰不到密碼。"""
    api = ptt.API(log_level=ptt.LogLevel.SILENT)
    try:
        api.login(username, password.get_secret_value(), kick_other_session=False)
    except Exception as exc:
        # NOTE: 原例外與其區域變數可能含帳密，只留類別名稱
        raise BbsLoginError(f"login failed: {type(exc).__name__}") from None
    install_send_throttle(api, now, sleep)
    return api


# ---------- 立即停止 ----------


def stop_reason(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name in _STOP_EXCEPTIONS else "unrecognized_error"


def check_screens(screens: Iterable[str]) -> None:
    for screen in screens:
        for keyword in _STOP_KEYWORDS:
            if keyword in screen:
                raise StopExperiment(f"screen_keyword:{keyword}")


class FailureTracker:
    def __init__(self) -> None:
        self._consecutive = 0

    def record(self, *, ok: bool) -> None:
        self._consecutive = 0 if ok else self._consecutive + 1
        if self._consecutive >= MAX_CONSECUTIVE_READ_FAILURES:
            raise StopExperiment("consecutive_read_failures")


# ---------- P0 閘門 ----------


def evaluate_p0(
    *,
    login_ok: bool,
    aid_ok: bool,
    boards_ok: Mapping[str, bool],
    seconds: Sequence[float],
    sends: Sequence[int],
) -> bool:
    return (
        login_ok
        and aid_ok
        and any(boards_ok.values())
        and all(s <= P0_MAX_SECONDS_PER_POST for s in seconds)
        and all(n <= P0_MAX_SENDS_PER_POST for n in sends)
    )


def require_p0(state: Mapping[str, Any]) -> None:
    if (state.get("p0") or {}).get("passed") is not True:
        raise P0NotPassed("P0 probe missing or failed; run `probe` first")


# ---------- C：U / L / E 與新推文辨識 ----------


@dataclass(frozen=True)
class Comment:
    type: str
    user_id: str
    content: str
    minute: datetime


@dataclass(frozen=True)
class Event:
    key: str
    u: float
    l: float  # noqa: E741 - 與開發規格 7.31 的 U/L/E 符號一致
    e: float
    t: datetime
    post: str = ""


def compute_ule(minute: datetime, seen: datetime) -> tuple[float, float, float]:
    u = (seen - minute).total_seconds()
    return u, max(0.0, u - 60), u - 30


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _base_key(c: Comment) -> str:
    return "|".join((c.type, c.user_id, _normalize(c.content), c.minute.isoformat()))


def make_event(comment: Comment, seen: datetime, post: str = "") -> Event:
    u, low, e = compute_ule(comment.minute, seen)
    return Event(key=_digest(_base_key(comment)), u=u, l=low, e=e, t=seen, post=post)


class CommentTracker:
    """第一次 observe 只建基準；之後沒看過的 (鍵, 第幾個) 才算新推文。"""

    def __init__(self, post: str = "") -> None:
        self._post = post
        self._known: set[str] = set()
        self._baseline_done = False

    def observe(self, comments: Iterable[Comment], seen: datetime) -> list[Event]:
        occurrences: Counter[str] = Counter()
        events: list[Event] = []
        for c in comments:
            base = _base_key(c)
            occurrences[base] += 1
            key = _digest(f"{base}#{occurrences[base]}")
            if key in self._known:
                continue
            self._known.add(key)
            if self._baseline_done:
                events.append(replace(make_event(c, seen, self._post), key=key))
        self._baseline_done = True
        return events


def p50(values: Sequence[float]) -> float:
    return sorted(values)[len(values) // 2]


def _p50_or_none(values: Sequence[float]) -> float | None:
    return p50(values) if values else None


@dataclass(frozen=True)
class WebComparison:
    diff_p50: float | None
    not_appeared: int
    unmatched_ratio: float
    usable: bool


def pair_with_web(bbs: Mapping[str, datetime], web: Mapping[str, datetime]) -> WebComparison:
    diffs = [(web[k] - t).total_seconds() for k, t in bbs.items() if k in web]
    missing = len(bbs) - len(diffs)
    ratio = missing / len(bbs) if bbs else 0.0
    return WebComparison(_p50_or_none(diffs), missing, ratio, ratio <= MAX_UNMATCHED_RATIO)


# ---------- C：樣本下限、容量、門檻 ----------


def sample_ok(phase: str, samples: int, posts: int) -> bool:
    if phase == "p1":
        return samples >= P1_MIN_SAMPLES
    return samples >= P2_MIN_SAMPLES and posts >= P2_MIN_POSTS


def n_max(avg_read_seconds: float) -> int:
    return math.floor(_CYCLE_BUDGET_SECONDS / (avg_read_seconds + _AVG_WAIT_SECONDS))


def needed_connections(avg_read_seconds: float, hot_concurrent_p90: int) -> int:
    return math.ceil(hot_concurrent_p90 / max(1, n_max(avg_read_seconds)))


@dataclass(frozen=True)
class Decision:
    recommend: bool
    criteria: dict[str, bool]


def decide(
    *,
    p2_e_p50: float | None,
    p2_samples: int,
    p2_posts: int,
    connections_needed: int,
    connections_proven: int,
    forbidden: bool | None,
    stop_triggered: bool,
) -> Decision:
    """forbidden=None（站規未確認）視為此項成立，報告另附「導入前確認站規」。"""
    latency = (
        p2_e_p50 is not None
        and p2_e_p50 <= P50_E_LIMIT_SECONDS
        and sample_ok("p2", p2_samples, p2_posts)
    )
    connections = connections_needed <= connections_proven
    rules = forbidden is not True and not stop_triggered
    criteria = {"latency": latency, "connections": connections, "rules": rules}
    return Decision(all(criteria.values()), criteria)


# ---------- summary.json（只有統計，沒有使用者 ID 與推文）----------


def _phase_entry(events: Sequence[Event]) -> dict[str, Any]:
    return {
        "samples": len(events),
        "posts": len({e.post for e in events}),
        "p50_l": _p50_or_none([e.l for e in events]),
        "p50_e": _p50_or_none([e.e for e in events]),
        "p50_u": _p50_or_none([e.u for e in events]),
    }


def build_summary(
    *,
    p1: Sequence[Event],
    p2: Sequence[Event],
    web: Sequence[Event],
    p0: Mapping[str, Any],
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"p0": dict(p0)}
    for phase, events in (("p1", p1), ("p2", p2)):
        entry = _phase_entry(events)
        entry["sample_ok"] = sample_ok(phase, entry["samples"], entry["posts"])
        summary[phase] = entry
    summary["web"] = _phase_entry(web)
    summary.update(extras or {})
    return summary


# ---------- 資料轉換 ----------


def _symbol(type_value: Any) -> str:  # noqa: ANN401 - PyPtt enum
    name = getattr(type_value, "name", str(type_value)).upper()
    return _TYPE_SYMBOLS.get(name, str(type_value))


def comments_from_bbs(
    raw_comments: Iterable[Mapping[Any, Any]],
    ptt: Any,  # noqa: ANN401 - PyPtt 模組
    post_created_at: datetime,
) -> tuple[list[Comment], int]:
    """PyPtt 的推文 → Comment；時間解析不出來的略過並回報數量（P0 問題 5）。"""
    comments: list[Comment] = []
    skipped = 0
    for raw in raw_comments:
        minute = parse_comment_time(str(raw[ptt.CommentField.time] or ""), post_created_at)
        if minute is None:
            skipped += 1
            continue
        comments.append(
            Comment(
                type=_symbol(raw[ptt.CommentField.type]),
                user_id=sanitize_screen(str(raw[ptt.CommentField.author] or "")).strip(),
                content=sanitize_screen(str(raw[ptt.CommentField.content] or "")),
                minute=minute,
            )
        )
    return comments, skipped


_WEB_SYMBOLS = {CommentType.PUSH: "推", CommentType.BOO: "噓", CommentType.ARROW: "→"}


def comments_from_web(html: str, url: str, crawled_at: datetime) -> list[Comment]:
    post = parse_post_page(
        html,
        board=split_post_id(post_id_from_url(url))[0],
        url=url,
        crawled_at=crawled_at,
        task_id=uuid.uuid4(),
    )
    return [
        Comment(_WEB_SYMBOLS[c.type], c.user_id or "", c.content or "", c.commented_at)
        for c in post.comments
        if c.commented_at is not None and c.type in _WEB_SYMBOLS
    ]


@dataclass(frozen=True)
class PostRef:
    url: str
    post_id: str
    board: str
    aid: str
    created_at: datetime


def parse_post_url(url: str, ptt: Any) -> PostRef:  # noqa: ANN401 - PyPtt 模組
    """URL 白名單（只收 www.ptt.cc 文章）；AID 用 PyPtt 的 lib_util 轉換。"""
    try:
        if urlparse(url).netloc != "www.ptt.cc":
            raise ParseError(url)
        post_id = post_id_from_url(url)
    except ParseError as e:
        raise SystemExit(f"not a PTT post url: {url}") from e
    board, filename = split_post_id(post_id)
    _, aid = ptt.lib_util.get_aid_from_url(url)
    return PostRef(url, post_id, board, aid, created_at_from_filename(filename))


# ---------- 讀取一篇 ----------


@dataclass(frozen=True)
class ReadResult:
    comments: list[Comment]
    at: datetime
    seconds: float
    sends: int
    screens: int
    skipped: int


class BbsReader:
    """連線只在這裡碰；單元測試以假 api 取代。"""

    def __init__(
        self,
        api: Any,  # noqa: ANN401
        ptt: Any,  # noqa: ANN401
        now: Callable[[], float],
        utcnow: Callable[[], datetime],
    ) -> None:
        self._api = api
        self._ptt = ptt
        self._now = now
        self._utcnow = utcnow

    def read(self, ref: PostRef) -> tuple[ReadResult, dict[Any, Any]]:
        throttle: SendThrottle = self._api.connect_core.send
        sends0, t0 = throttle.count, self._now()
        post = self._api.get_post(ref.board, aid=ref.aid)
        at, seconds = self._utcnow(), self._now() - t0
        screens = [sanitize_screen(s) for s in self._api.connect_core.get_screen_queue()]
        check_screens(screens)
        comments, skipped = comments_from_bbs(
            post.get(self._ptt.PostField.comments) or [], self._ptt, ref.created_at
        )
        result = ReadResult(comments, at, seconds, throttle.count - sends0, len(screens), skipped)
        return result, post


# ---------- 實驗流程 ----------


@dataclass
class Store:
    """寫入 <run_dir>/*.jsonl；多執行緒共用。"""

    run_dir: Path
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def append(self, name: str, record: Mapping[str, Any]) -> None:
        with self._lock, (self.run_dir / name).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def write(self, name: str, data: Mapping[str, Any]) -> None:
        with self._lock:
            (self.run_dir / name).write_text(
                json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )


def _event_record(phase: str, ev: Event) -> dict[str, Any]:
    return {"phase": phase, **asdict(ev), "t": ev.t.isoformat()}


def run_phase(
    phase: str,
    refs: Sequence[PostRef],
    duration_seconds: float,
    *,
    read: Callable[[PostRef], ReadResult],
    pacer: ReadPacer,
    trackers: Mapping[str, CommentTracker],
    failures: FailureTracker,
    store: Store,
    clock: Callable[[], float],
) -> None:
    """輪流讀 refs 直到時間到；停止條件以例外往上丟。"""
    end = clock() + duration_seconds
    i = 0
    while clock() < end:
        ref = refs[i % len(refs)]
        i += 1
        pacer.wait()
        try:
            res = read(ref)
        except StopExperiment:
            raise
        except Exception as exc:
            if type(exc).__name__ not in _READ_FAILURE_EXCEPTIONS:
                raise StopExperiment(stop_reason(exc)) from None
            failures.record(ok=False)
            store.append("reads.jsonl", {"phase": phase, "post": ref.post_id, "ok": False})
            pacer.mark_done()
            continue
        pacer.mark_done()
        failures.record(ok=True)
        store.append(
            "reads.jsonl",
            {
                "phase": phase,
                "post": ref.post_id,
                "ok": True,
                "seconds": res.seconds,
                "sends": res.sends,
                "screens": res.screens,
                "comments": len(res.comments),
                "time_unparsed": res.skipped,
                "at": res.at.isoformat(),
            },
        )
        for ev in trackers[ref.post_id].observe(res.comments, res.at):
            store.append("events.jsonl", _event_record(phase, ev))


class WebPoller(threading.Thread):
    """每篇每 60 秒 1 次的網頁版對照；不繞過快取（用 PttClient）。"""

    def __init__(
        self,
        refs: Sequence[PostRef],
        fetch: Callable[[str], tuple[int, str]],
        store: Store,
        utcnow: Callable[[], datetime],
        interval: float = WEB_POLL_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(daemon=True)
        self._refs = refs
        self._fetch = fetch
        self._store = store
        self._utcnow = utcnow
        self._interval = interval
        self._trackers = {r.post_id: CommentTracker(r.post_id) for r in refs}
        self.stop_flag = threading.Event()

    def poll_once(self) -> None:
        for ref in self._refs:
            try:
                status, html = self._fetch(ref.url)
                if status != 200:
                    log.warning(f"web poll {ref.post_id}: status {status}")
                    continue
                at = self._utcnow()
                comments = comments_from_web(html, ref.url, at)
            except Exception as exc:  # 暫時性錯誤不中斷對照
                log.warning(f"web poll {ref.post_id} failed: {type(exc).__name__}")
                continue
            for ev in self._trackers[ref.post_id].observe(comments, at):
                self._store.append("events.jsonl", _event_record("web", ev))

    def run(self) -> None:
        while not self.stop_flag.is_set():
            self.poll_once()
            self.stop_flag.wait(self._interval)


def clock_offset_seconds(url: str, utcnow: Callable[[], datetime]) -> float | None:
    """本機時鐘 − 網頁版 Date 標頭（秒）；只發 1 個請求。"""
    import httpx2

    try:
        resp = httpx2.get(
            url, headers={"User-Agent": USER_AGENT}, cookies=OVER18_COOKIE, timeout=10
        )
        server = parsedate_to_datetime(resp.headers["Date"])
    except Exception as exc:
        log.warning(f"clock check failed: {type(exc).__name__}")
        return None
    return (utcnow() - server).total_seconds()


# ---------- 指令 ----------


def load_credentials() -> tuple[str, SecretStr]:
    username, password = os.environ.get(_USERNAME_VAR), os.environ.get(_PASSWORD_VAR)
    missing = [n for n, v in ((_USERNAME_VAR, username), (_PASSWORD_VAR, password)) if not v]
    if missing:
        raise SystemExit(f"missing environment variable(s): {', '.join(missing)}")
    return username or "", SecretStr(password or "")


def _load_pyptt() -> ModuleType:
    import PyPtt  # 延遲 import：沒裝 bbs-spike group 時其他功能與測試仍可用

    return PyPtt


def _login(out: Path) -> tuple[Any, Any, Ledger, str, SecretStr]:
    username, password = load_credentials()
    ledger = Ledger(out / "ledger.jsonl")
    check_login_allowed(ledger.attempts(), datetime.now(UTC))
    ptt = _load_pyptt()
    ledger.record(datetime.now(UTC), "attempt")
    api = open_session(ptt, username, password, time.monotonic, time.sleep)
    return api, ptt, ledger, username, password


def _logout(api: Any) -> None:  # noqa: ANN401
    try:
        api.logout()
    except Exception as exc:
        log.warning(f"logout failed: {type(exc).__name__}")


def cmd_probe(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    p0: dict[str, Any] = {
        "login_ok": False,
        "aid_ok": True,
        "boards_ok": {},
        "seconds": [],
        "sends": [],
        "comments": [],
        "time_unparsed": 0,
        "time_sample": None,
        "ip_present": False,
        "at": datetime.now(UTC).isoformat(),
    }
    username, password = load_credentials()
    api = None
    try:
        api, ptt, _, username, password = _login(out)
        p0["login_ok"] = True
        reader = BbsReader(api, ptt, time.monotonic, lambda: datetime.now(UTC))
        pacer = ReadPacer(time.monotonic, time.sleep)
        for url in args.url:
            ref = parse_post_url(url, ptt)
            pacer.wait()
            try:
                res, post = reader.read(ref)
            except StopExperiment:
                raise
            except Exception as exc:
                if type(exc).__name__ not in _READ_FAILURE_EXCEPTIONS:
                    raise StopExperiment(stop_reason(exc)) from None
                p0["boards_ok"][ref.board] = False
                pacer.mark_done()
                continue
            pacer.mark_done()
            p0["boards_ok"][ref.board] = True
            p0["aid_ok"] = p0["aid_ok"] and post.get(ptt.PostField.url) == url
            p0["seconds"].append(round(res.seconds, 1))
            p0["sends"].append(res.sends)
            p0["comments"].append(len(res.comments) + res.skipped)
            p0["time_unparsed"] += res.skipped
            raw = post.get(ptt.PostField.comments) or []
            if raw and p0["time_sample"] is None:
                p0["time_sample"] = re.sub(r"\d", "9", str(raw[0][ptt.CommentField.time]))
            p0["ip_present"] = p0["ip_present"] or any(c[ptt.CommentField.ip] for c in raw)
    except StopExperiment as stop:
        p0["stop_reason"] = stop.reason
        _say(f"STOP: {stop.reason}")
    except LoginRefused as refused:
        _say(f"refused: {refused}")
        return 3
    finally:
        if api is not None:
            _logout(api)
    p0["passed"] = evaluate_p0(
        login_ok=p0["login_ok"],
        aid_ok=p0["aid_ok"],
        boards_ok=p0["boards_ok"],
        seconds=p0["seconds"],
        sends=p0["sends"],
    )
    (out / "p0.json").write_text(json.dumps({"p0": p0}, indent=2), encoding="utf-8")
    code = finish_output_check(out, username, password.get_secret_value())
    _say(f"P0 passed={p0['passed']} boards={p0['boards_ok']} sends={p0['sends']}")
    return code or (0 if p0["passed"] else 1)


def cmd_run(args: argparse.Namespace) -> int:
    out = Path(args.out)
    try:
        state = json.loads((out / "p0.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        state = {}
    try:
        require_p0(state)
    except P0NotPassed as e:
        _say(f"refused: {e}")
        return 3
    username, password = load_credentials()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    store = Store(run_dir)
    api = poller = None
    stop_reason_text: str | None = None
    try:
        api, ptt, _, username, password = _login(out)
        refs = [parse_post_url(u, ptt) for u in args.url]
        offset = clock_offset_seconds(refs[0].url, lambda: datetime.now(UTC))
        store.write("meta.json", {"run_id": run_id, "posts": [r.post_id for r in refs]})
        store.write("clock.json", {"offset_seconds": offset})
        poller = WebPoller(refs, _web_fetcher(), store, lambda: datetime.now(UTC))
        poller.start()
        reader = BbsReader(api, ptt, time.monotonic, lambda: datetime.now(UTC))
        trackers = {r.post_id: CommentTracker(r.post_id) for r in refs}
        common = {
            "read": lambda ref: reader.read(ref)[0],
            "pacer": ReadPacer(time.monotonic, time.sleep),
            "trackers": trackers,
            "failures": FailureTracker(),
            "store": store,
            "clock": time.monotonic,
        }
        run_phase("p1", refs[:1], args.p1_minutes * 60, **common)
        run_phase("p2", refs, args.p2_minutes * 60, **common)
    except KeyboardInterrupt:
        stop_reason_text = "interrupted"
    except StopExperiment as stop:
        stop_reason_text = stop.reason
    except LoginRefused as refused:
        _say(f"refused: {refused}")
        return 3
    finally:
        if api is not None:
            _logout(api)
    if stop_reason_text:
        store.write("stop.json", {"reason": stop_reason_text})
        _say(f"STOP: {stop_reason_text}")
    elif poller is not None:
        _say(f"BBS done; web tail {args.tail_minutes} min")
        time.sleep(args.tail_minutes * 60)
    if poller is not None:
        poller.stop_flag.set()
        poller.join(timeout=WEB_POLL_INTERVAL_SECONDS)
    code = finish_output_check(out, username, password.get_secret_value())
    _say(f"run_id={run_id}")
    return code


def _web_fetcher() -> Callable[[str], tuple[int, str]]:
    client = PttClient(RateLimiter())

    def fetch(url: str) -> tuple[int, str]:
        result = client.fetch(url)
        return result.status, result.html

    return fetch


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _events(records: Iterable[Mapping[str, Any]], phase: str) -> list[Event]:
    return [
        Event(r["key"], r["u"], r["l"], r["e"], datetime.fromisoformat(r["t"]), r["post"])
        for r in records
        if r["phase"] == phase
    ]


def cmd_summarize(args: argparse.Namespace) -> int:
    out = Path(args.out)
    run_dir = out / args.run_id
    records = _read_jsonl(run_dir / "events.jsonl")
    p1, p2, web = (_events(records, p) for p in ("p1", "p2", "web"))
    reads = [r for r in _read_jsonl(run_dir / "reads.jsonl") if r["ok"]]
    p0 = json.loads((out / "p0.json").read_text(encoding="utf-8"))["p0"]
    stop = (run_dir / "stop.json").exists()
    seconds = [r["seconds"] for r in reads if r["phase"] == "p2"]
    avg_read = sum(seconds) / len(seconds) if seconds else 0.0
    bbs = {e.key: e.t for e in (*p1, *p2)}
    cmp_ = pair_with_web(bbs, {e.key: e.t for e in web})
    offset = json.loads((run_dir / "clock.json").read_text(encoding="utf-8"))["offset_seconds"]
    forbidden = {"forbidden": True, "allowed": False, "unconfirmed": None}[args.rules]
    needed = needed_connections(avg_read, args.hot_concurrent_p90)
    phase2 = _phase_entry(p2)
    decision = decide(
        p2_e_p50=phase2["p50_e"],
        p2_samples=phase2["samples"],
        p2_posts=phase2["posts"],
        connections_needed=needed,
        connections_proven=args.connections_proven,
        forbidden=forbidden,
        stop_triggered=stop,
    )
    extras = {
        "web_pairing": asdict(cmp_),
        "clock_offset_seconds": offset,
        "clock_offset_flag": offset is not None and abs(offset) > CLOCK_SKEW_LIMIT_SECONDS,
        "capacity": {
            "avg_read_seconds": avg_read,
            "reads": len(reads),
            "avg_sends": _mean([r["sends"] for r in reads]),
            "avg_screens": _mean([r["screens"] for r in reads]),
            "n_max": n_max(avg_read),
            "hot_concurrent_p90": args.hot_concurrent_p90,
            "connections_needed": needed,
        },
        "rules": args.rules,
        "stop_triggered": stop,
        "decision": {"recommend": decision.recommend, **decision.criteria},
    }
    summary = build_summary(p1=p1, p2=p2, web=web, p0=p0, extras=extras)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _say(json.dumps(summary["decision"]) + f"  -> {run_dir / 'summary.json'}")
    return 0


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--out", default=_DEFAULT_OUT, help="輸出目錄（含 ledger.jsonl）")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="P0 探測")
    probe.add_argument("--url", nargs="+", required=True, help="每個目標看板一篇文章 URL")
    run = sub.add_parser("run", help="P1、P2 與網頁版尾段")
    run.add_argument("--url", nargs=3, required=True, help="熱門文章 URL，3 篇；第 1 篇做 P1")
    run.add_argument("--p1-minutes", type=float, default=10)
    run.add_argument("--p2-minutes", type=float, default=30)
    run.add_argument("--tail-minutes", type=float, default=20)
    summ = sub.add_parser("summarize", help="由原始資料算 summary.json")
    summ.add_argument("--run-id", required=True)
    summ.add_argument("--hot-concurrent-p90", type=int, required=True)
    summ.add_argument(
        "--rules", choices=["forbidden", "allowed", "unconfirmed"], default="unconfirmed"
    )
    summ.add_argument("--connections-proven", type=int, default=1)
    return parser.parse_args(argv)


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "probe": cmd_probe,
    "run": cmd_run,
    "summarize": cmd_summarize,
}


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("bbs-spike")
    args = parse_args()
    sys.exit(COMMANDS[args.command](args))


if __name__ == "__main__":
    main()

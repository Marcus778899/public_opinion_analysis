"""PTT BBS 延遲實驗（一次性，由甲方手動執行，開發規格 7.31）。全程唯讀，不進測試與 CI。

用法（帳密只讀環境變數 PTT_BBS_USERNAME、PTT_BBS_PASSWORD）：
  uv run --group bbs-spike --env-file .env python tools/bbs_spike.py probe --url <各看板一篇>...
  uv run --group bbs-spike --env-file .env python tools/bbs_spike.py run --url <熱門文章 3 篇>
  uv run python tools/bbs_spike.py summarize --run-id <id> --hot-concurrent-p90 <n>
補實驗（開發規格 7.31 G）：
  uv run --group bbs-spike --env-file .env python tools/bbs_spike.py retest --url <4 篇>
  uv run --group bbs-spike python tools/bbs_spike.py summarize-retest --run-id <id> \
    --hot-concurrent-p90 <n>
"""

import argparse
import hashlib
import json
import logging
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
from datetime import UTC, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from functools import partial
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

# ---------- 補實驗（7.31 G） ----------
RETEST_POSTS = 4
R2_MIN_SECONDS = 2400
R2_MAX_SECONDS = 3600
R2_MIN_SAMPLES = 100
R2_MIN_POSTS = 3
SLOW_READ_INTERVAL_SECONDS = 60
OPEN_GAP_SECONDS = MIN_LOGIN_INTERVAL_SECONDS + 5
PROOF_MAX_SECONDS = 600
TAIL_SECONDS = 1200
MAX_POST_AGE_SECONDS = 3600
MIN_WEB_SCORE = 30
HOT_WINDOW_SECONDS = 600
HOT_MIN_COMMENTS = 10
EVENING_START_SECONDS = 20 * 3600
EVENING_END_SECONDS = 21 * 3600 + 45 * 60
_TAIPEI = timezone(timedelta(hours=8))
_TIME_EPSILON = 1e-6

_USERNAME_VAR = "PTT_BBS_USERNAME"
_PASSWORD_VAR = "PTT_BBS_PASSWORD"
_STOP_EXCEPTIONS = frozenset(
    {"UseTooManyResources", "LoginTooOften", "UserHasPreviouslyBeenBanned", "WrongIDorPassword"}
)
_STOP_KEYWORDS = ("登入太頻繁", "系統過載")
# NOTE: 新連線自己的登入畫面本來就有這些字，只查「已開著的連線」（7.31 G-3a）
_MULTI_LOGIN_KEYWORDS = ("重複登入", "其它連線已登入", "其他連線已登入")
_READ_FAILURE_EXCEPTIONS = frozenset({"NoSuchPost", "NoSuchBoard", "NoPermission"})
_ANSI_RE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|[@-Z\\-_])")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_TYPE_SYMBOLS = {"PUSH": "推", "BOO": "噓", "ARROW": "→"}
_DEFAULT_OUT = "data/spike/bbs"
_RETEST_OUT = "data/spike/bbs-retest"
_DEFAULT_P0 = "data/spike/bbs/p0.json"
_LEDGER_NAME = "ledger.jsonl"


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


def _secret_pattern(value: str) -> re.Pattern[bytes]:
    """值緊貼英數字時不算洩漏（短帳號會誤中雜湊鍵）；值本身以非英數字開頭／結尾則該側不檢查。"""
    raw = re.escape(value.encode())
    before = rb"(?<![0-9A-Za-z])" if value[0].isascii() and value[0].isalnum() else b""
    after = rb"(?![0-9A-Za-z])" if value[-1].isascii() and value[-1].isalnum() else b""
    return re.compile(before + raw + after)


def _find_leaks(root: Path, secrets: Mapping[str, str]) -> list[tuple[Path, list[str]]]:
    """secrets 為 值 → 名稱；含值的檔案刪除，回傳（路徑, 名稱）。空值不比對。"""
    leaks: list[tuple[Path, list[str]]] = []
    if not root.exists():
        return leaks
    patterns = {v: _secret_pattern(v) for v in secrets if v}
    # NOTE: ledger 刪了等於拿掉登入上限；內容固定為時間、固定字詞與 conn（O-2）
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != _LEDGER_NAME):
        data = path.read_bytes()
        names = [name for value, name in secrets.items() if value and patterns[value].search(data)]
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

    def record(self, at: datetime, result: str, conn: str | None = None) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        row: dict[str, str] = {"at": at.isoformat(), "result": result}
        if conn is not None:
            row["conn"] = conn
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def update_last(self, result: str) -> None:
        """登入結束後把最後一筆的結果改成 ok／失敗原因；不新增一筆，次數才不會多算。"""
        lines = self._path.read_text(encoding="utf-8").splitlines()
        last = json.loads(lines[-1])
        last["result"] = result
        lines[-1] = json.dumps(last)
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
    _silence_pyptt_logger()
    try:
        api.login(username, password.get_secret_value(), kick_other_session=False)
    except Exception as exc:
        # NOTE: 原例外與其區域變數可能含帳密，只留類別名稱
        raise BbsLoginError(f"login failed: {type(exc).__name__}") from None
    install_send_throttle(api, now, sleep)
    try:
        check_screens(recent_screens(api, require_rdq=True))
    except StopExperiment as stop:
        # NOTE: PyPtt 對「登入太頻繁」只按鍵繼續，登入仍成功；這裡自己比對畫面佇列
        _safe_logout(api)
        raise BbsLoginError(f"login failed: {stop.reason}") from None
    return api


def _silence_pyptt_logger() -> None:
    """PyPtt 建 API 時會掛 console handler；換成 NullHandler，終端機才不會有輸出（O-1）。"""
    logger = logging.getLogger("PyPtt")
    logger.handlers[:] = [logging.NullHandler()]
    logger.propagate = False


def recent_screens(api: Any, *, require_rdq: bool = False) -> list[str]:  # noqa: ANN401
    """最近 10 個畫面（PyPtt 內部 _RDQ；get_screen_queue 只回 1 個）；只比對、不存檔。"""
    core = api.connect_core
    queue = getattr(core, "_RDQ", None)
    if queue is not None:
        return [sanitize_screen(str(x)) for x in queue.get(10)]
    getter = None if require_rdq else getattr(core, "get_screen_queue", None)
    return [sanitize_screen(str(x)) for x in getter()] if getter else []


def _safe_logout(api: Any) -> None:  # noqa: ANN401
    try:
        api.logout()
    except Exception as exc:
        log.warning(f"logout failed: {type(exc).__name__}")


# ---------- 立即停止 ----------


def stop_reason(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name in _STOP_EXCEPTIONS else "unrecognized_error"


def check_screens(screens: Iterable[str]) -> None:
    for screen in screens:
        for keyword in _STOP_KEYWORDS:
            if keyword in screen:
                raise StopExperiment(f"screen_keyword:{keyword}")


def check_multi_login(screens: Iterable[str]) -> None:
    for screen in screens:
        for keyword in _MULTI_LOGIN_KEYWORDS:
            if keyword in screen:
                raise StopExperiment("multi_login_warning")


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
        screens = recent_screens(self._api)
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


def _read_record(phase: str, ref: PostRef, res: ReadResult) -> dict[str, Any]:
    return {
        "phase": phase,
        "post": ref.post_id,
        "ok": True,
        "seconds": res.seconds,
        "sends": res.sends,
        "screens": res.screens,
        "comments": len(res.comments),
        "time_unparsed": res.skipped,
        "at": res.at.isoformat(),
    }


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
        store.append("reads.jsonl", _read_record(phase, ref, res))
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


def _parse_refs(urls: Sequence[str], ptt: Any) -> list[PostRef]:  # noqa: ANN401
    """登入前先驗證全部 URL，打錯字才不會白用一次登入。"""
    refs = []
    for url in urls:
        try:
            refs.append(parse_post_url(url, ptt))
        except SystemExit:
            raise
        except Exception as exc:
            raise SystemExit(f"invalid url ({type(exc).__name__}): {url}") from None
    return refs


def _login_with(
    ledger: Ledger,
    ptt: Any,  # noqa: ANN401
    username: str,
    password: SecretStr,
    conn: str | None = None,
) -> Any:  # noqa: ANN401
    """檢查上限、記 ledger、登入一次；失敗把原因寫回 ledger 後往上丟。"""
    check_login_allowed(ledger.attempts(), datetime.now(UTC))
    ledger.record(datetime.now(UTC), "attempt", conn)
    try:
        api = open_session(ptt, username, password, time.monotonic, time.sleep)
    except BbsLoginError as e:
        ledger.update_last(f"failed: {e}")
        raise
    ledger.update_last("ok")
    return api


def _login(out: Path, ptt: Any) -> tuple[Any, Ledger, str, SecretStr]:  # noqa: ANN401
    username, password = load_credentials()
    ledger = Ledger(out / _LEDGER_NAME)
    api = _login_with(ledger, ptt, username, password)
    return api, ledger, username, password


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
    ptt = _load_pyptt()
    refs = _parse_refs(args.url, ptt)
    api = None
    try:
        api, _, username, password = _login(out, ptt)
        p0["login_ok"] = True
        reader = BbsReader(api, ptt, time.monotonic, lambda: datetime.now(UTC))
        pacer = ReadPacer(time.monotonic, time.sleep)
        for ref in refs:
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
            p0["aid_ok"] = p0["aid_ok"] and post.get(ptt.PostField.url) == ref.url
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
    ptt = _load_pyptt()
    refs = _parse_refs(args.url, ptt)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = out / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    store = Store(run_dir)
    api = poller = None
    stop_reason_text: str | None = None
    try:
        api, _, username, password = _login(out, ptt)
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
        try:
            time.sleep(args.tail_minutes * 60)
        except KeyboardInterrupt:
            log.warning("tail interrupted")
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


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


# ---------- 合格文章（7.31 G-4 #2）：發文 ≤ 60 分鐘且任一 10 分鐘內新推文 ≥ 10 ----------


def run_started_at(run_id: str) -> datetime | None:
    """run_id 即開始時間（UTC）；格式不符回傳 None。"""
    try:
        return datetime.strptime(run_id, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def is_hot(minutes: Sequence[datetime]) -> bool:
    ordered = sorted(minutes)
    window = timedelta(seconds=HOT_WINDOW_SECONDS)
    return any(
        ordered[i + HOT_MIN_COMMENTS - 1] - ordered[i] < window
        for i in range(len(ordered) - HOT_MIN_COMMENTS + 1)
    )


def _post_age_seconds(post_id: str, started: datetime | None) -> float | None:
    if started is None:
        return None
    try:
        created = created_at_from_filename(split_post_id(post_id)[1])
    except ValueError:
        return None
    return (started - created).total_seconds()


def qualify_posts(
    posts: Sequence[str],
    started: datetime | None,
    bbs: Sequence[Event],
    web: Sequence[Event],
) -> tuple[set[str], list[dict[str, str]]]:
    """回傳（合格的 post_id, 不合格的 post_id 與原因）；推文鍵取 BBS 與網頁版的聯集。"""
    qualified: set[str] = set()
    excluded: list[dict[str, str]] = []
    for post in dict.fromkeys(posts):
        age = _post_age_seconds(post, started)
        if age is None:
            reason = "post_age_unknown"
        elif age > MAX_POST_AGE_SECONDS:
            reason = "posted_more_than_60_minutes_before_start"
        else:
            minutes = {e.key: e.t - timedelta(seconds=e.u) for e in (*bbs, *web) if e.post == post}
            reason = (
                "" if is_hot(list(minutes.values())) else "fewer_than_10_comments_in_10_minutes"
            )
        if reason:
            excluded.append({"post_id": post, "reason": reason})
        else:
            qualified.add(post)
    return qualified, excluded


def _run_posts(run_dir: Path, records: Sequence[Mapping[str, Any]]) -> list[str]:
    meta = run_dir / "meta.json"
    posts: list[str] = (
        list(json.loads(meta.read_text(encoding="utf-8"))["posts"]) if (meta.exists()) else []
    )
    return [*posts, *sorted({r["post"] for r in records} - set(posts))]


def _capacity_entry(reads: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    seconds = [r["seconds"] for r in reads]
    return {
        "avg_read_seconds": sum(seconds) / len(seconds) if seconds else 0.0,
        "reads": len(reads),
        "avg_sends": _mean([r["sends"] for r in reads]),
        "avg_screens": _mean([r["screens"] for r in reads]),
    }


def _capacity(reads: Sequence[Mapping[str, Any]], phase: str, p90: int) -> dict[str, Any]:
    """容量只用判定階段的讀取（#327）；全程平均另放 capacity_all。"""
    entry = _capacity_entry([r for r in reads if r["phase"] == phase])
    return {
        **entry,
        "n_max": n_max(entry["avg_read_seconds"]),
        "hot_concurrent_p90": p90,
        "connections_needed": needed_connections(entry["avg_read_seconds"], p90),
    }


def _forbidden(rules: str) -> bool | None:
    return {"forbidden": True, "allowed": False, "unconfirmed": None}[rules]


def _write_summary(run_dir: Path, summary: Mapping[str, Any]) -> None:
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _say(json.dumps(summary["decision"]) + f"  -> {run_dir / 'summary.json'}")


def _clock_offset(run_dir: Path) -> float | None:
    path = run_dir / "clock.json"
    return json.loads(path.read_text(encoding="utf-8"))["offset_seconds"] if path.exists() else None


def cmd_summarize(args: argparse.Namespace) -> int:
    out = Path(args.out)
    run_dir = out / args.run_id
    records = _read_jsonl(run_dir / "events.jsonl")
    p1, p2, web = (_events(records, p) for p in ("p1", "p2", "web"))
    qualified, excluded = qualify_posts(
        _run_posts(run_dir, records), run_started_at(args.run_id), [*p1, *p2], web
    )
    p1, p2, web = ([e for e in es if e.post in qualified] for es in (p1, p2, web))
    reads = [r for r in _read_jsonl(run_dir / "reads.jsonl") if r["ok"]]
    p0 = json.loads((out / "p0.json").read_text(encoding="utf-8"))["p0"]
    stop = (run_dir / "stop.json").exists()
    capacity = _capacity(reads, "p2", args.hot_concurrent_p90)
    bbs = {e.key: e.t for e in (*p1, *p2)}
    web = [e for e in web if e.key in bbs]  # 7.31 C：只比同一批推文
    cmp_ = pair_with_web(bbs, {e.key: e.t for e in web})
    offset = _clock_offset(run_dir)
    phase2 = _phase_entry(p2)
    decision = decide(
        p2_e_p50=phase2["p50_e"],
        p2_samples=phase2["samples"],
        p2_posts=phase2["posts"],
        connections_needed=capacity["connections_needed"],
        connections_proven=args.connections_proven,
        forbidden=_forbidden(args.rules),
        stop_triggered=stop,
    )
    extras = {
        "web_pairing": asdict(cmp_),
        "clock_offset_seconds": offset,
        "clock_offset_flag": offset is not None and abs(offset) > CLOCK_SKEW_LIMIT_SECONDS,
        "capacity": capacity,
        "capacity_all": _capacity_entry(reads),
        "excluded": excluded,
        "rules": args.rules,
        "stop_triggered": stop,
        "decision": {"recommend": decision.recommend, **decision.criteria},
    }
    _write_summary(run_dir, build_summary(p1=p1, p2=p2, web=web, p0=p0, extras=extras))
    return 0


# ---------- 補實驗的判定與 summary（7.31 G-5） ----------


def r2_sample_ok(samples: int, posts: int) -> bool:
    return samples >= R2_MIN_SAMPLES and posts >= R2_MIN_POSTS


def decide_retest(
    *,
    e_p50: float | None,
    samples: int,
    posts: int,
    polled_posts: int,
    connections_proven: int,
    forbidden: bool | None,
    stop_triggered: bool,
) -> Decision:
    """R1 延遲、R2 連線（混合方案用 1 條）、R3 站規與 R2 立即停止；M 階段的停止不影響 R3。"""
    latency = (
        e_p50 is not None
        and e_p50 <= P50_E_LIMIT_SECONDS
        and r2_sample_ok(samples, posts)
        and polled_posts == RETEST_POSTS
    )
    criteria = {
        "latency": latency,
        "connections": connections_proven >= 1,
        "rules": forbidden is not True and not stop_triggered,
    }
    return Decision(all(criteria.values()), criteria)


def cmd_summarize_retest(args: argparse.Namespace) -> int:
    run_dir = Path(args.out) / args.run_id
    records = _read_jsonl(run_dir / "events.jsonl")
    r2, web = (_events(records, p) for p in ("r2", "web"))  # M 階段的事件不進判定
    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    polled = list(meta["posts"])
    qualified, excluded = qualify_posts(polled, run_started_at(args.run_id), r2, web)
    r2 = [e for e in r2 if e.post in qualified]
    reads = [r for r in _read_jsonl(run_dir / "reads.jsonl") if r["ok"]]
    conn_path = run_dir / "connections.json"
    connections = (
        json.loads(conn_path.read_text(encoding="utf-8"))
        if conn_path.exists()
        else {"tested": 0, "proven": 0, "stop_reason": "connections.json missing"}
    )
    stop = (run_dir / "stop.json").exists()
    bbs = {e.key: e.t for e in r2}
    web = [e for e in web if e.key in bbs and e.post in qualified]
    cmp_ = pair_with_web(bbs, {e.key: e.t for e in web})
    offset = _clock_offset(run_dir)
    entry = _phase_entry(r2)
    entry["sample_ok"] = r2_sample_ok(entry["samples"], entry["posts"]) and len(polled) == (
        RETEST_POSTS
    )
    proven = int(connections["proven"])
    p90 = args.hot_concurrent_p90
    covered = RETEST_POSTS * proven
    decision = decide_retest(
        e_p50=entry["p50_e"],
        samples=entry["samples"],
        posts=entry["posts"],
        polled_posts=len(polled),
        connections_proven=proven,
        forbidden=_forbidden(args.rules),
        stop_triggered=stop,
    )
    summary = {
        "r2": entry,
        "web": _phase_entry(web),
        "web_pairing": asdict(cmp_),
        "clock_offset_seconds": offset,
        "clock_offset_flag": offset is not None and abs(offset) > CLOCK_SKEW_LIMIT_SECONDS,
        "capacity": _capacity(reads, "r2", p90),
        "capacity_all": _capacity_entry(reads),
        "excluded": excluded,
        "connections": connections,
        "mixed": {
            "posts_per_connection": RETEST_POSTS,
            "covered_posts": covered,
            "coverage_of_p90": covered / p90 if p90 else None,
        },
        "rules": args.rules,
        "stop_triggered": stop,
        "decision": {"recommend": decision.recommend, **decision.criteria},
    }
    _write_summary(run_dir, summary)
    return 0


# ---------- 補實驗的登入前檢查（7.31 G-2） ----------


class RetestRefused(Exception):
    """登入前檢查沒過；沒有登入、沒有寫 ledger。"""


@dataclass(frozen=True)
class RetestPlan:
    ptt: Any
    refs: list[PostRef]
    connections: int
    username: str
    password: SecretStr
    fetch: Callable[[str], tuple[int, str]]
    started: datetime


def check_start_window(now: datetime) -> None:
    local = now.astimezone(_TAIPEI)
    seconds = local.hour * 3600 + local.minute * 60 + local.second
    if not EVENING_START_SECONDS <= seconds < EVENING_END_SECONDS:
        raise RetestRefused("start time must be within 20:00-21:45 Asia/Taipei")


def web_score(html: str, url: str, now: datetime) -> int:
    """推 − 噓；列表上的推文數就是這個值。"""
    post = parse_post_page(
        html,
        board=split_post_id(post_id_from_url(url))[0],
        url=url,
        crawled_at=now,
        task_id=uuid.uuid4(),
    )
    types = [c.type for c in post.comments]
    return types.count(CommentType.PUSH) - types.count(CommentType.BOO)


def _check_posts(refs: Sequence[PostRef], boards_ok: Mapping[str, bool], now: datetime) -> None:
    if len({r.post_id for r in refs}) != len(refs):
        raise RetestRefused("urls must be distinct")
    for ref in refs:
        if boards_ok.get(ref.board) is not True:
            raise RetestRefused(f"board {ref.board} was not proven by the first experiment p0")
        if (now - ref.created_at).total_seconds() > MAX_POST_AGE_SECONDS:
            raise RetestRefused(f"{ref.post_id} was posted more than 60 minutes ago")


def _check_web_scores(
    refs: Sequence[PostRef], fetch: Callable[[str], tuple[int, str]], now: datetime
) -> None:
    for ref in refs:
        try:
            status, html = fetch(ref.url)
            score = web_score(html, ref.url, now) if status == 200 else None
        except Exception as exc:
            raise RetestRefused(f"web page check failed ({type(exc).__name__})") from None
        if score is None or score < MIN_WEB_SCORE:
            raise RetestRefused(f"{ref.post_id} has fewer than {MIN_WEB_SCORE} net pushes")


def retest_precheck(args: argparse.Namespace) -> RetestPlan:
    out, p0_path = Path(args.out), Path(args.p0)
    if out.resolve() == p0_path.resolve().parent:
        raise RetestRefused("--out must not be the directory of --p0 (first experiment data)")
    try:
        state = json.loads(p0_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    try:
        require_p0(state)
    except P0NotPassed as e:
        raise RetestRefused(str(e)) from None
    ptt = _load_pyptt()
    now = datetime.now(UTC)
    check_start_window(now)
    refs = _parse_refs(args.url, ptt)
    _check_posts(refs, state["p0"].get("boards_ok") or {}, now)
    fetch = _web_fetcher()
    _check_web_scores(refs, fetch, now)
    attempts = Ledger(out / _LEDGER_NAME).attempts()
    check_login_allowed(attempts, now)
    username, password = load_credentials()
    connections = min(args.connections, MAX_LOGINS - len(attempts))
    return RetestPlan(ptt, refs, connections, username, password, fetch, now)


# ---------- 補實驗的連線排程（7.31 G-2、G-3、G-3a） ----------


@dataclass
class Conn:
    name: str
    api: Any
    reader: BbsReader
    min_gap: float
    jitter: float
    opened_at: float
    ready_at: float
    failures: FailureTracker = field(default_factory=FailureTracker)
    cursor: int = 0


class RetestSession:
    """所有連線與網頁版對照都在同一個執行緒依序操作，同時只有一個請求在跑。"""

    def __init__(self, plan: RetestPlan, store: Store, ledger: Ledger) -> None:
        self.plan, self.store, self.ledger = plan, store, ledger
        self.web = WebPoller(plan.refs, plan.fetch, store, lambda: datetime.now(UTC))
        self.trackers = {r.post_id: CommentTracker(r.post_id) for r in plan.refs}
        self.conns: list[Conn] = []
        self.phase = "r2"
        self.tested = 0
        self.proven = 0
        self.proved: set[str] = set()
        self.r2_samples = 0
        self.r2_posts: set[str] = set()
        self.web_next = math.inf  # 第一次 BBS 讀取完才開始對照

    def open_conn(self, name: str) -> Conn:
        self.tested += 1
        opened = time.monotonic()
        try:
            api = _login_with(
                self.ledger, self.plan.ptt, self.plan.username, self.plan.password, name
            )
        except LoginRefused:
            raise StopExperiment("login_refused") from None
        reader = BbsReader(api, self.plan.ptt, time.monotonic, lambda: datetime.now(UTC))
        fast = name == "A"
        conn = Conn(
            name,
            api,
            reader,
            MIN_READ_INTERVAL_SECONDS if fast else SLOW_READ_INTERVAL_SECONDS,
            READ_JITTER_MAX_SECONDS if fast else 0,
            opened,
            time.monotonic(),
        )
        self.conns.append(conn)
        self.proved = set()
        return conn

    def _is_old(self, conn: Conn) -> bool:
        return len(self.conns) > 1 and conn is not self.conns[-1]

    def _failure_reason(self, conn: Conn, exc: Exception) -> str:
        base = stop_reason(exc)
        if len(self.conns) == 1:
            return base
        if base == "unrecognized_error" and self._is_old(conn):
            return f"kicked_or_closed:{conn.name}"
        return f"{base}:{conn.name}"

    def _schedule(self, conn: Conn) -> None:
        conn.ready_at = time.monotonic() + conn.min_gap + random.uniform(0, conn.jitter)

    def read_once(self, conn: Conn) -> None:
        ref = self.plan.refs[conn.cursor % len(self.plan.refs)]
        conn.cursor += 1
        try:
            res = conn.reader.read(ref)[0]
        except StopExperiment:
            raise
        except Exception as exc:
            if type(exc).__name__ not in _READ_FAILURE_EXCEPTIONS:
                raise StopExperiment(self._failure_reason(conn, exc)) from None
            conn.failures.record(ok=False)
            self.store.append(
                "reads.jsonl", {"phase": self.phase, "post": ref.post_id, "ok": False}
            )
            self._schedule(conn)
            return
        conn.failures.record(ok=True)
        self.store.append("reads.jsonl", _read_record(self.phase, ref, res))
        if conn.name == "A":
            for ev in self.trackers[ref.post_id].observe(res.comments, res.at):
                self.store.append("events.jsonl", _event_record(self.phase, ev))
                if self.phase == "r2":
                    self.r2_samples += 1
                    self.r2_posts.add(ev.post)
        if self._is_old(conn):
            try:
                check_multi_login(recent_screens(conn.api))
            except StopExperiment as stop:
                raise StopExperiment(f"{stop.reason}:{conn.name}") from None
        self.proved.add(conn.name)
        self._schedule(conn)
        if math.isinf(self.web_next):
            self.web_next = time.monotonic()

    def poll_web(self) -> None:
        self.web_next = time.monotonic() + WEB_POLL_INTERVAL_SECONDS
        self.web.poll_once()

    def drive(self, until: Callable[[], bool], deadline: float | None = None) -> None:
        """時間最早的動作先做（各連線讀取、網頁版對照）；until 成立或到 deadline 就回來。"""
        while not until():
            now = time.monotonic()
            if deadline is not None and now >= deadline - _TIME_EPSILON:
                return
            conn = min(self.conns, key=lambda c: c.ready_at)
            target = min(conn.ready_at, self.web_next)
            if deadline is not None:
                target = min(target, deadline)
            if target - now > _TIME_EPSILON:
                time.sleep(target - now)
                continue
            if self.web_next < conn.ready_at and self.web_next - now <= _TIME_EPSILON:
                self.poll_web()
            elif conn.ready_at - now <= _TIME_EPSILON:
                self.read_once(conn)

    def r2_enough(self) -> bool:
        return r2_sample_ok(self.r2_samples, len(self.r2_posts))

    def run_r2(self) -> bool:
        """跑 40～60 分鐘；回傳樣本是否足夠（不足時不開 B、C，D-051）。"""
        first = self.conns[0]
        self.phase = "r2"
        self.drive(
            lambda: time.monotonic() - first.opened_at >= R2_MIN_SECONDS and self.r2_enough(),
            first.opened_at + R2_MAX_SECONDS,
        )
        self.proven = 1
        return self.r2_enough()

    def run_m(self, total: int) -> None:
        self.phase = "m"
        for name in ("B", "C")[: total - 1]:
            self.drive(lambda: False, self.conns[-1].opened_at + OPEN_GAP_SECONDS)
            conn = self.open_conn(name)
            names = {c.name for c in self.conns}
            self.drive(partial(self.proved.issuperset, names), conn.opened_at + PROOF_MAX_SECONDS)
            if not self.proved >= names:
                raise StopExperiment("not_proven_in_time")
            self.proven = len(self.conns)

    def logout_all(self) -> None:
        for conn in self.conns:
            _logout(conn.api)

    def web_tail(self) -> None:
        end = time.monotonic() + TAIL_SECONDS
        while True:
            started = time.monotonic()
            self.web.poll_once()
            remaining = end - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(
                min(remaining, max(0.0, WEB_POLL_INTERVAL_SECONDS - (time.monotonic() - started)))
            )


def cmd_retest(args: argparse.Namespace) -> int:
    out = Path(args.out)
    try:
        plan = retest_precheck(args)
    except (RetestRefused, LoginRefused) as refused:
        _say(f"refused: {refused}")
        return 3
    run_id = plan.started.strftime("%Y%m%dT%H%M%SZ")
    run_dir = out / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    store = Store(run_dir)
    session = RetestSession(plan, store, Ledger(out / _LEDGER_NAME))
    stop: str | None = None
    try:
        session.open_conn("A")
        offset = clock_offset_seconds(plan.refs[0].url, lambda: datetime.now(UTC))
        store.write("meta.json", {"run_id": run_id, "posts": [r.post_id for r in plan.refs]})
        store.write("clock.json", {"offset_seconds": offset})
        if not session.run_r2():
            stop = "r2_samples_insufficient"
        elif plan.connections > 1:
            session.run_m(plan.connections)
    except KeyboardInterrupt:
        stop = "interrupted"
    except StopExperiment as e:
        stop = e.reason
    finally:
        session.logout_all()
    r2_stopped = stop is not None and session.proven == 0
    store.write(
        "connections.json",
        {"tested": session.tested, "proven": session.proven, "stop_reason": stop},
    )
    if r2_stopped:
        store.write("stop.json", {"reason": stop})
        _say(f"STOP: {stop}")
    else:
        _say(f"BBS done ({stop or 'complete'}); web tail {TAIL_SECONDS // 60} min")
        try:
            session.web_tail()
        except KeyboardInterrupt:
            log.warning("tail interrupted")
    code = finish_output_check(out, plan.username, plan.password.get_secret_value())
    _say(f"run_id={run_id}")
    return code or (1 if r2_stopped else 0)


# ---------- 指令列 ----------


def _connections_arg(value: str) -> int:
    number = int(value)
    if not 1 <= number <= MAX_LOGINS:
        raise argparse.ArgumentTypeError(f"must be 1-{MAX_LOGINS}")
    return number


def _add_out(parser: argparse.ArgumentParser, default: str) -> None:
    # NOTE: SUPPRESS 讓子命令前的 --out 不被子命令的預設值蓋掉
    parser.add_argument(
        "--out",
        default=argparse.SUPPRESS,
        help=f"輸出目錄，放 ledger.jsonl 與各次執行的資料夾；預設 {default}；子命令前後都可以放",
    )


def _add_summarize_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True, help="執行編號，即輸出目錄下的資料夾名稱")
    parser.add_argument(
        "--hot-concurrent-p90",
        type=int,
        required=True,
        help="同時熱門文章篇數的 p90（篇），取自 bbs-hot-articles-stat",
    )
    parser.add_argument(
        "--rules",
        choices=["forbidden", "allowed", "unconfirmed"],
        default="unconfirmed",
        help="站規狀態 forbidden／allowed／unconfirmed，預設 unconfirmed（未確認，視為不擋）",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--out", default=None, help="輸出目錄；各子命令的預設值不同，見子命令的說明"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="P0 探測")
    probe.add_argument("--url", nargs="+", required=True, help="每個目標看板一篇文章 URL")
    _add_out(probe, _DEFAULT_OUT)
    run = sub.add_parser("run", help="P1、P2 與網頁版尾段")
    run.add_argument("--url", nargs=3, required=True, help="熱門文章 URL，3 篇；第 1 篇做 P1")
    run.add_argument("--p1-minutes", type=float, default=10, help="P1 長度（分鐘），預設 10")
    run.add_argument("--p2-minutes", type=float, default=30, help="P2 長度（分鐘），預設 30")
    run.add_argument("--tail-minutes", type=float, default=20, help="網頁版尾段（分鐘），預設 20")
    _add_out(run, _DEFAULT_OUT)
    summ = sub.add_parser("summarize", help="由原始資料算 summary.json")
    _add_summarize_options(summ)
    summ.add_argument(
        "--connections-proven",
        type=int,
        default=1,
        help="已證實的同時登入數（條），預設 1（D-044）",
    )
    _add_out(summ, _DEFAULT_OUT)
    retest = sub.add_parser("retest", help="補實驗：R2 混合延遲、M 同帳號連線數、網頁版尾段")
    retest.add_argument("--url", nargs=RETEST_POSTS, required=True, help="熱門文章 URL，恰 4 篇")
    retest.add_argument(
        "--connections",
        type=_connections_arg,
        default=MAX_LOGINS,
        help="要測到幾條連線（條，1～3），預設 3；實際取此值與 ledger 剩餘次數的較小者",
    )
    retest.add_argument(
        "--p0", default=_DEFAULT_P0, help=f"第一次實驗的 p0.json（只讀），預設 {_DEFAULT_P0}"
    )
    _add_out(retest, _RETEST_OUT)
    summ_re = sub.add_parser("summarize-retest", help="由補實驗的原始資料算 summary.json")
    _add_summarize_options(summ_re)
    _add_out(summ_re, _RETEST_OUT)
    args = parser.parse_args(argv)
    if args.out is None:
        args.out = _RETEST_OUT if args.command in ("retest", "summarize-retest") else _DEFAULT_OUT
    return args


COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "probe": cmd_probe,
    "run": cmd_run,
    "summarize": cmd_summarize,
    "retest": cmd_retest,
    "summarize-retest": cmd_summarize_retest,
}


@log.catch(level="CRITICAL")
def main() -> None:
    setup_logging("bbs-spike")
    args = parse_args()
    sys.exit(COMMANDS[args.command](args))


if __name__ == "__main__":
    main()

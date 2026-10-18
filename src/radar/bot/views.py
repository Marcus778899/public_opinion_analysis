"""每個畫面是「查詢結果 → 文字與按鈕」的純函式（開發規格 7.23）；文字為 HTML。

callback_data 格式：<版本>:<動作>:<參數>，上限 64 bytes。
"""

import html
from dataclasses import dataclass, field
from enum import StrEnum

from radar.bot.stats import CONTROVERSY_MIN_VOTES, BoardOverview, HotPost, PostSentiment, PostStats
from radar.bot.telegram import Button, Keyboard
from radar.common.ids import PTT_BASE_URL, split_post_id
from radar.common.schemas import Alert

CALLBACK_VERSION = "1"
MAX_CALLBACK_BYTES = 64
# 看板警示列出的文章數（設計文件 9.2）
ALERT_TOP_POSTS = 3
POLARITY_LABELS = {"negative": "負面", "neutral": "中立", "positive": "正面"}
QUERY_FAILED = "查詢失敗，請稍後再試"


class Action(StrEnum):
    MENU = "menu"
    HOT = "hot"  # 參數 "all" 代表全部看板，否則只看訂閱的
    SUBS = "subs"
    SUB = "sub"  # 切換訂閱，參數是看板
    BOARDS = "boards"  # 看板概況的看板清單
    OVERVIEW = "ov"  # 參數是看板
    SETTINGS = "set"
    TOGGLE = "tog"  # 切換警示類型，參數 "post"／"board"
    MUTE = "mute"  # 參數是 post_id
    UNMUTE = "unmute"


@dataclass(frozen=True)
class Callback:
    action: Action
    arg: str = ""


@dataclass(frozen=True)
class Screen:
    text: str
    keyboard: Keyboard = field(default_factory=list)


@dataclass(frozen=True)
class ChatPrefs:
    post_alerts: bool = True
    board_alerts: bool = True


def encode_callback(action: Action, arg: str = "") -> str:
    """超過 64 bytes 拋 ValueError（Bot API 會拒絕整則訊息）。"""
    data = f"{CALLBACK_VERSION}:{action.value}:{arg}"
    if len(data.encode()) > MAX_CALLBACK_BYTES:
        raise ValueError(f"callback_data longer than {MAX_CALLBACK_BYTES} bytes: {data!r}")
    return data


def parse_callback(data: str | None) -> Callback | None:
    """版本不符、動作未知、格式錯誤都回傳 None（呼叫端顯示「選單已過期」）。"""
    parts = (data or "").split(":", 2)
    if len(parts) != 3 or parts[0] != CALLBACK_VERSION:
        return None
    try:
        return Callback(Action(parts[1]), parts[2])
    except ValueError:
        return None


def post_url(post_id: str) -> str:
    """Gossiping.M.1.A.ABC → https://www.ptt.cc/bbs/Gossiping/M.1.A.ABC.html。"""
    board, filename = split_post_id(post_id)
    return f"{PTT_BASE_URL}/bbs/{board}/{filename}.html"


def escape(text: str) -> str:
    return html.escape(text, quote=False)


def ratio(value: float, baseline: float) -> float:
    """平常的幾倍；基準小於 1 時以 1 計，避免除以接近 0 的數。"""
    return value / max(baseline, 1.0)


def controversy(push: int, boo: int) -> float | None:
    """噓 ÷（推＋噓）；推＋噓少於 CONTROVERSY_MIN_VOTES 時回傳 None（不顯示）。"""
    votes = push + boo
    if votes < CONTROVERSY_MIN_VOTES:
        return None
    return boo / votes


def sentiment_text(sentiment: PostSentiment | None, min_score: float) -> str:
    """「負面 72%」；分數低於 min_score 為「不確定」；沒有推論為「尚無」。"""
    if sentiment is None:
        return "尚無"
    if sentiment.score < min_score:
        return "不確定"
    label = POLARITY_LABELS.get(sentiment.polarity, sentiment.polarity)
    return f"{label} {sentiment.score:.0%}"


def post_link(post_id: str, title: str | None) -> str:
    return f'<a href="{post_url(post_id)}">{escape(title or post_id)}</a>'


def post_line(stats: PostStats, min_score: float) -> str:
    """一篇文章的摘要：標題（連結）、推／噓／箭頭、爭議度、情緒。"""
    parts = [f"推 {stats.push}", f"噓 {stats.boo}", f"→ {stats.arrow}"]
    share = controversy(stats.push, stats.boo)
    if share is not None:
        parts.append(f"爭議 {share:.0%}")
    parts.append(f"情緒 {sentiment_text(stats.sentiment, min_score)}")
    return f"{post_link(stats.post_id, stats.title)}\n{'｜'.join(parts)}"


def _nav(text: str, action: Action, arg: str = "") -> Button:
    return Button(text, callback_data=encode_callback(action, arg))


def _menu_row() -> list[Button]:
    return [_nav("⬅️ 主選單", Action.MENU)]


def main_menu(notice: str | None = None) -> Screen:
    """🔥 現在熱門、📋 我的訂閱、📈 看板概況、⚙️ 通知設定；notice 顯示在最上面。"""
    lines = [escape(notice)] if notice else []
    lines.append("<b>PTT 輿情雷達</b>：請選擇")
    keyboard = [
        [_nav("🔥 現在熱門", Action.HOT), _nav("📋 我的訂閱", Action.SUBS)],
        [_nav("📈 看板概況", Action.BOARDS), _nav("⚙️ 通知設定", Action.SETTINGS)],
    ]
    return Screen("\n".join(lines), keyboard)


def expired_screen() -> Screen:
    return main_menu("選單已過期，請重新選擇")


def hot_screen(posts: list[HotPost], *, all_boards: bool, min_score: float) -> Screen:
    """文章各一個「開啟原文」URL 按鈕；切換「全部看板／只看訂閱」與返回主選單。"""
    scope = "全部看板" if all_boards else "訂閱的看板"
    lines = [f"🔥 <b>現在熱門</b>（{scope}）"]
    if not posts:
        lines.append("最近沒有推文")
    for i, hot in enumerate(posts, 1):
        board = escape(hot.stats.board)
        lines.append(f"{i}. [{board}] 新增 {hot.recent} 則\n{post_line(hot.stats, min_score)}")
    keyboard: Keyboard = [
        [Button(f"{i}. 開啟原文", url=post_url(h.stats.post_id))] for i, h in enumerate(posts, 1)
    ]
    toggle = _nav("只看訂閱", Action.HOT) if all_boards else _nav("全部看板", Action.HOT, "all")
    keyboard.append([toggle, *_menu_row()])
    return Screen("\n\n".join(lines), keyboard)


def _pairs(buttons: list[Button]) -> Keyboard:
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def subscriptions_screen(boards: list[str], mine: set[str]) -> Screen:
    """每個啟用的看板一個按鈕，✅／⬜ 標示是否已訂閱，點一下切換。"""
    if not boards:
        return Screen("目前沒有可訂閱的看板", [_menu_row()])
    buttons = [_nav(f"{'✅' if b in mine else '⬜'} {b}", Action.SUB, b) for b in boards]
    text = "📋 <b>我的訂閱</b>：點看板切換；推文暴增時通知你"
    return Screen(text, [*_pairs(buttons), _menu_row()])


def board_picker_screen(boards: list[str]) -> Screen:
    """看板概況：先選看板。"""
    if not boards:
        return Screen("目前沒有啟用的看板", [_menu_row()])
    buttons = [_nav(b, Action.OVERVIEW, b) for b in boards]
    return Screen("📈 <b>看板概況</b>：選擇看板", [*_pairs(buttons), _menu_row()])


def board_overview_screen(overview: BoardOverview, min_score: float) -> Screen:
    """情緒比例附「n 篇有推論」；沒有推論的文章不算進比例。"""
    board = escape(overview.board)
    lines = [
        f"📈 <b>[{board}] 近 24 小時</b>",
        f"文章 {overview.posts_24h} 篇｜推文 {overview.comments_24h} 則｜"
        f"今天 {overview.alerts_today} 則警示",
    ]
    predicted = sum(overview.sentiments.values())
    if predicted:
        shares = "｜".join(
            f"{label} {overview.sentiments.get(key, 0) / predicted:.0%}"
            for key, label in POLARITY_LABELS.items()
        )
        lines.append(f"情緒（{predicted} 篇有推論）：{shares}")
    else:
        lines.append("情緒：尚無推論")
    if overview.top_controversial:
        lines.append("爭議度最高：")
        lines += [
            f"{i}. {post_line(p, min_score)}" for i, p in enumerate(overview.top_controversial, 1)
        ]
    keyboard = [
        [_nav("🔄 重新整理", Action.OVERVIEW, overview.board), _nav("⬅️ 看板清單", Action.BOARDS)],
        _menu_row(),
    ]
    return Screen("\n".join(lines), keyboard)


def settings_screen(prefs: ChatPrefs, muted: list[PostStats | str]) -> Screen:
    """文章警示、看板警示的開關；「不再通知」的文章各一個恢復按鈕（查不到標題時只有 post_id）。"""
    lines = ["⚙️ <b>通知設定</b>：點一下切換"]
    keyboard: Keyboard = [
        [_nav(f"{'✅' if prefs.post_alerts else '⬜'} 文章警示", Action.TOGGLE, "post")],
        [_nav(f"{'✅' if prefs.board_alerts else '⬜'} 看板警示", Action.TOGGLE, "board")],
    ]
    if muted:
        lines.append("不再通知的文章（點按鈕恢復）：")
    for item in muted:
        post_id, title = (item, None) if isinstance(item, str) else (item.post_id, item.title)
        lines.append(f"• {post_link(post_id, title)}")
        label = (title or post_id)[:24]
        keyboard.append([_nav(f"🔔 恢復：{label}", Action.UNMUTE, post_id)])
    keyboard.append(_menu_row())
    return Screen("\n".join(lines), keyboard)


def alert_screen(alert: Alert, stats: dict[str, PostStats], min_score: float) -> Screen:
    """推文數與平常的倍數；文章警示帶推噓與情緒，看板警示列前 3 篇。stats 為空時只有基本資訊。

    按鈕：開啟原文、看板概況、訂閱設定；文章警示另有「這篇不再通知」。
    """
    board = escape(alert.board)
    minutes = round((alert.window_end - alert.window_start).total_seconds() / 60)
    times = ratio(alert.value, alert.baseline)
    times_text = f"{times:.0f}" if times >= 10 else f"{times:.1f}"
    heat = f"{minutes} 分鐘內 {alert.value} 則推文，平常的 {times_text} 倍"
    if alert.unit_type == "post":
        post_ids = [alert.unit_key]
        lines = [f"🔥 <b>[{board}] 文章推文暴增</b>", heat]
    else:
        post_ids = alert.sample_post_ids[:ALERT_TOP_POSTS]
        lines = [f"📈 <b>[{board}] 看板推文量暴增</b>", heat, "熱門文章："]
    for i, post_id in enumerate(post_ids, 1):
        found = stats.get(post_id)
        line = post_line(found, min_score) if found else post_link(post_id, None)
        lines.append(line if alert.unit_type == "post" else f"{i}. {line}")
    keyboard: Keyboard
    if alert.unit_type == "post":
        keyboard = [
            [Button("開啟原文", url=post_url(alert.unit_key))],
            [_nav("🔕 這篇不再通知", Action.MUTE, alert.unit_key)],
        ]
    else:
        keyboard = [[Button(f"{i}. 開啟原文", url=post_url(p)) for i, p in enumerate(post_ids, 1)]]
    keyboard.append(
        [_nav("📈 看板概況", Action.OVERVIEW, alert.board), _nav("📋 訂閱設定", Action.SUBS)]
    )
    return Screen("\n".join(lines), keyboard)

"""按鈕回呼的處理（開發規格 7.23）：Callback → 要顯示的畫面與短提示；不呼叫 Telegram。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from radar.bot.repository import PreferenceRepository, SubscriptionRepository
from radar.bot.stats import QUERY_ERRORS, PostStats, Queries
from radar.bot.views import (
    QUERY_FAILED,
    Action,
    Callback,
    Screen,
    board_overview_screen,
    board_picker_screen,
    expired_screen,
    hot_screen,
    main_menu,
    settings_screen,
    subscriptions_screen,
)
from radar.common.ids import split_post_id
from radar.common.log import log

TOGGLE_LABELS = {"post": "文章警示", "board": "看板警示"}


@dataclass(frozen=True)
class CallbackResult:
    # None 代表不改訊息（例如「這篇不再通知」只回提示）
    screen: Screen | None
    toast: str | None = None
    # True 代表 toast 已經透過 answer 送出，呼叫端不要再 answer
    answered: bool = False


def handle_callback(
    callback: Callback | None,
    chat_id: int,
    subs: SubscriptionRepository,
    prefs: PreferenceRepository,
    queries: Queries,
    *,
    min_score: float,
    now: datetime,
    answer: Callable[[str | None], None] | None = None,
) -> CallbackResult:
    """callback 為 None（解析失敗、版本不符）時回傳 expired_screen。

    現在熱門預設只看訂閱的看板；沒有訂閱時改看全部看板。
    """
    if callback is None:
        return CallbackResult(expired_screen())
    action, arg = callback.action, callback.arg
    try:
        if action is Action.MENU:
            return CallbackResult(main_menu())
        if action is Action.HOT:
            return CallbackResult(_hot(arg == "all", chat_id, subs, queries, min_score))
        if action is Action.SUBS:
            return CallbackResult(_subscriptions(chat_id, subs))
        if action is Action.SUB:
            return _toggle_subscription(arg, chat_id, subs, answer)
        if action is Action.BOARDS:
            return CallbackResult(board_picker_screen(subs.enabled_boards()))
        if action is Action.OVERVIEW:
            if arg not in subs.enabled_boards():
                return CallbackResult(None, f"找不到看板 {arg}")
            return CallbackResult(board_overview_screen(queries.overview(arg, now), min_score))
        if action is Action.SETTINGS:
            return CallbackResult(_settings(chat_id, prefs, queries))
        if action is Action.TOGGLE:
            return _toggle_alerts(arg, chat_id, prefs, queries)
        return _mute(action, arg, chat_id, prefs, queries)
    except QUERY_ERRORS as e:
        log.warning("query for %s failed: %s", action.value, e)
        return CallbackResult(None, QUERY_FAILED)


def _hot(
    all_boards: bool,
    chat_id: int,
    subs: SubscriptionRepository,
    queries: Queries,
    min_score: float,
) -> Screen:
    mine = [] if all_boards else subs.boards_of(chat_id)
    posts = queries.hot(mine or None)
    return hot_screen(posts, all_boards=not mine, min_score=min_score)


def _subscriptions(chat_id: int, subs: SubscriptionRepository) -> Screen:
    return subscriptions_screen(subs.enabled_boards(), set(subs.boards_of(chat_id)))


def _toggle_subscription(
    board: str,
    chat_id: int,
    subs: SubscriptionRepository,
    answer: Callable[[str | None], None] | None = None,
) -> CallbackResult:
    """寫入後先 answer（有給的話），再重查畫面；重查沿用已查過的看板清單。"""
    enabled = subs.enabled_boards()
    if board not in enabled:
        return CallbackResult(None, f"找不到看板 {board}")
    if board in subs.boards_of(chat_id):
        subs.unsubscribe(chat_id, board)
        toast = f"已取消 {board}"
    else:
        subs.subscribe(chat_id, board)
        toast = f"已訂閱 {board}"
    if answer is not None:
        answer(toast)
    screen = subscriptions_screen(enabled, set(subs.boards_of(chat_id)))
    return CallbackResult(screen, toast, answered=answer is not None)


def _settings(chat_id: int, prefs: PreferenceRepository, queries: Queries) -> Screen:
    """查不到標題（含查詢失敗）時只顯示 post_id，設定畫面照樣能用。"""
    muted = prefs.muted(chat_id)
    try:
        stats = queries.post_stats(muted)
    except QUERY_ERRORS as e:
        log.warning("muted post titles query failed: %s", e)
        stats = {}
    items: list[PostStats | str] = [stats.get(p) or p for p in muted]
    return settings_screen(prefs.prefs(chat_id), items)


def _toggle_alerts(
    unit_type: str, chat_id: int, prefs: PreferenceRepository, queries: Queries
) -> CallbackResult:
    if unit_type not in TOGGLE_LABELS:
        return CallbackResult(expired_screen())
    current = prefs.toggle(chat_id, "post" if unit_type == "post" else "board")
    enabled = current.post_alerts if unit_type == "post" else current.board_alerts
    toast = f"已{'開啟' if enabled else '關閉'}{TOGGLE_LABELS[unit_type]}"
    return CallbackResult(_settings(chat_id, prefs, queries), toast)


def _mute(
    action: Action, post_id: str, chat_id: int, prefs: PreferenceRepository, queries: Queries
) -> CallbackResult:
    """MUTE 從警示按，只回提示；UNMUTE 從設定畫面按，重畫設定畫面。"""
    try:
        split_post_id(post_id)
    except ValueError:
        return CallbackResult(None, "無法辨識這篇文章")
    if action is Action.MUTE:
        prefs.mute(chat_id, post_id)
        return CallbackResult(None, "這篇不再通知")
    prefs.unmute(chat_id, post_id)
    return CallbackResult(_settings(chat_id, prefs, queries), "已恢復通知")

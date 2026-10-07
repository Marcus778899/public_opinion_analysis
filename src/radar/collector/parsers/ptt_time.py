"""PTT 頁面上的時間格式；頁面時間皆為 Asia/Taipei，一律轉成 UTC（開發規格 2.1）。"""

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

PTT_TZ = ZoneInfo("Asia/Taipei")

_FILENAME_EPOCH_RE = re.compile(r"^M\.(\d+)\.A\.[0-9A-Fa-f]{3}$")
_COMMENT_TIME_RE = re.compile(r"(\d{1,2})/(\d{1,2})\s+(\d{1,2}):(\d{2})\s*$")
_MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTHS = {name: i for i, name in enumerate(_MONTH_NAMES, 1)}


def parse_article_time(text: str) -> datetime | None:
    """文章標頭的時間，例："Tue Oct  7 12:34:56 2026"；格式不符回傳 None。"""
    # NOTE: 不用 strptime 的 %a/%b，避免受系統 locale 影響
    parts = text.split()
    if len(parts) != 5 or parts[1] not in _MONTHS:
        return None
    try:
        hour, minute, second = (int(x) for x in parts[3].split(":"))
        local = datetime(int(parts[4]), _MONTHS[parts[1]], int(parts[2]), hour, minute, second)
    except ValueError:
        return None
    return local.replace(tzinfo=PTT_TZ).astimezone(UTC)


def created_at_from_filename(filename: str) -> datetime:
    """檔名 M.<epoch>.A.xxx 的 epoch 即發文時間；標頭缺漏或格式錯誤時的備援。"""
    match = _FILENAME_EPOCH_RE.fullmatch(filename)
    if not match:
        raise ValueError(f"invalid PTT filename: {filename!r}")
    return datetime.fromtimestamp(int(match.group(1)), UTC)


def parse_comment_time(text: str, post_created_at: datetime) -> datetime | None:
    """推文時間，例："10/07 12:35"，前面可能帶 IP；沒有年份，以文章時間推算。

    推文月份小於文章月份時視為跨年（開發規格 2.1）；解析不出來回傳 None。
    """
    match = _COMMENT_TIME_RE.search(text)
    if not match:
        return None
    month, day, hour, minute = (int(g) for g in match.groups())
    post_local = post_created_at.astimezone(PTT_TZ)
    year = post_local.year + (1 if month < post_local.month else 0)
    try:
        local = datetime(year, month, day, hour, minute, tzinfo=PTT_TZ)
    except ValueError:
        return None
    return local.astimezone(UTC)

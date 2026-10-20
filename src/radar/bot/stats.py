"""bot 畫面與警示用的 ClickHouse 查詢（開發規格 7.23）；結果轉成 dataclass 給 views。"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import httpx2

from radar.common.clickhouse import ClickHouseClient, ClickHouseError
from radar.common.ids import split_post_id

# 查詢失敗時警示照樣推送（不帶推噓與情緒），呼叫端攔這些例外
QUERY_ERRORS = (ClickHouseError, httpx2.TransportError)
# 推＋噓少於這個數不算爭議度（開發規格 7.23）
CONTROVERSY_MIN_VOTES = 10
OVERVIEW_TOP = 3
_BOARD_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
TAIPEI = ZoneInfo("Asia/Taipei")

# NOTE: LEFT JOIN 沒對到時填預設值（0、''），polarity 為 '' 代表沒有推論
POST_STATS_QUERY = """
SELECT p.post_id AS post_id, p.board AS board, p.title AS title,
       c.push AS push, c.boo AS boo, c.arrow AS arrow, s.polarity AS polarity, s.score AS score
FROM (
    SELECT post_id, board, title FROM posts_latest FINAL
    WHERE post_id IN {post_ids:Array(String)}
) AS p
LEFT JOIN (
    SELECT post_id, countIf(type = 'push') AS push, countIf(type = 'boo') AS boo,
           countIf(type = 'arrow') AS arrow
    FROM comments_latest FINAL
    WHERE is_deleted = 0 AND post_id IN {post_ids:Array(String)}
    GROUP BY post_id
) AS c ON c.post_id = p.post_id
LEFT JOIN (
    SELECT post_id, argMax(polarity, predicted_at) AS polarity,
           argMax(arrayMax(mapValues(scores)), predicted_at) AS score
    FROM predictions
    WHERE post_id IN {post_ids:Array(String)}
    GROUP BY post_id
) AS s ON s.post_id = p.post_id
"""

HOT_QUERY = """
SELECT post_id, count() AS recent
FROM comments_latest FINAL
WHERE is_deleted = 0 AND commented_at >= now() - INTERVAL {window_min:UInt32} MINUTE
  AND (empty({boards:Array(String)}) OR board IN {boards:Array(String)})
GROUP BY post_id
ORDER BY recent DESC, post_id
LIMIT {limit:UInt32}
"""

OVERVIEW_QUERY = """
SELECT
    (SELECT count() FROM posts_latest FINAL
     WHERE board = {board:String} AND created_at >= {since:DateTime64(6, 'UTC')}) AS posts,
    (SELECT count() FROM comments_latest FINAL
     WHERE board = {board:String} AND is_deleted = 0
       AND commented_at >= {since:DateTime64(6, 'UTC')}) AS comments,
    (SELECT uniqExact(alert_id) FROM alerts
     WHERE board = {board:String} AND created_at >= {today:DateTime64(6, 'UTC')}) AS alerts
"""

# 近 24 小時發文的文章：最新一筆推論的 polarity
SENTIMENT_QUERY = """
SELECT polarity, count() AS n
FROM (
    SELECT post_id, argMax(polarity, predicted_at) AS polarity
    FROM predictions
    WHERE post_id IN (
        SELECT post_id FROM posts_latest FINAL
        WHERE board = {board:String} AND created_at >= {since:DateTime64(6, 'UTC')}
    )
    GROUP BY post_id
)
GROUP BY polarity
"""

CONTROVERSIAL_QUERY = """
SELECT post_id, countIf(type = 'boo') / count() AS share
FROM comments_latest FINAL
WHERE is_deleted = 0 AND type IN ('push', 'boo') AND post_id IN (
    SELECT post_id FROM posts_latest FINAL
    WHERE board = {board:String} AND created_at >= {since:DateTime64(6, 'UTC')}
)
GROUP BY post_id
HAVING count() >= {min_votes:UInt32}
ORDER BY share DESC, post_id
LIMIT {limit:UInt32}
"""


@dataclass(frozen=True)
class PostSentiment:
    polarity: str
    # 三類分數中最高的那個
    score: float


@dataclass(frozen=True)
class PostStats:
    post_id: str
    board: str
    title: str | None
    push: int
    boo: int
    arrow: int
    sentiment: PostSentiment | None


@dataclass(frozen=True)
class HotPost:
    stats: PostStats
    # 最近 window_min 分鐘新增的推文數
    recent: int


@dataclass(frozen=True)
class BoardOverview:
    board: str
    posts_24h: int
    comments_24h: int
    # polarity → 篇數；只算有推論的文章
    sentiments: dict[str, int]
    top_controversial: list[PostStats]
    alerts_today: int


def post_ids_literal(post_ids: list[str]) -> str:
    """ClickHouse Array(String) 參數的字面值；post_id 先驗證格式，不含引號。"""
    for post_id in post_ids:
        split_post_id(post_id)
    return "[" + ",".join(f"'{p}'" for p in post_ids) + "]"


def boards_literal(boards: list[str]) -> str:
    """看板名稱的 Array(String) 字面值；只允許 PTT 看板名稱的字元。"""
    for board in boards:
        if not _BOARD_NAME.fullmatch(board):
            raise ValueError(f"invalid board name: {board!r}")
    return "[" + ",".join(f"'{b}'" for b in boards) + "]"


def _datetime(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S.%f")


def _sentiment(row: dict[str, Any]) -> PostSentiment | None:
    if not row.get("polarity"):
        return None
    return PostSentiment(str(row["polarity"]), float(row["score"]))


class Queries(Protocol):
    """callbacks 與 notify 依賴的查詢；單元測試以 fake 取代。"""

    def post_stats(self, post_ids: list[str]) -> dict[str, PostStats]: ...

    def hot(self, boards: list[str] | None) -> list[HotPost]: ...

    def overview(self, board: str, now: datetime) -> BoardOverview: ...


class ClickHouseQueries:
    def __init__(self, client: ClickHouseClient, *, hot_window_min: int, hot_limit: int) -> None:
        self._client = client
        self._hot_window_min = hot_window_min
        self._hot_limit = hot_limit

    def post_stats(self, post_ids: list[str]) -> dict[str, PostStats]:
        """標題、推／噓／箭頭數（comments_latest FINAL 依 type）、最新一筆推論。"""
        if not post_ids:
            return {}
        rows = self._client.query_rows(POST_STATS_QUERY, {"post_ids": post_ids_literal(post_ids)})
        return {
            str(r["post_id"]): PostStats(
                post_id=str(r["post_id"]),
                board=str(r["board"]),
                title=r["title"] or None,
                push=int(r["push"]),
                boo=int(r["boo"]),
                arrow=int(r["arrow"]),
                sentiment=_sentiment(r),
            )
            for r in rows
        }

    def hot(self, boards: list[str] | None) -> list[HotPost]:
        """最近 hot_window_min 分鐘新增推文最多的 hot_limit 篇；boards 為 None 代表全部看板。"""
        params = {
            "window_min": str(self._hot_window_min),
            "limit": str(self._hot_limit),
            "boards": boards_literal(boards or []),
        }
        rows = self._client.query_rows(HOT_QUERY, params)
        recent = {str(r["post_id"]): int(r["recent"]) for r in rows}
        stats = self.post_stats(list(recent))
        # NOTE: 推文比文章先進 ClickHouse 時查不到標題，仍列出（只有 post_id）
        return [
            HotPost(stats.get(p) or PostStats(p, split_post_id(p)[0], None, 0, 0, 0, None), n)
            for p, n in recent.items()
        ]

    def overview(self, board: str, now: datetime) -> BoardOverview:
        """近 24 小時的文章數、推文數、情緒分布、爭議度前 3 篇；今天（Asia/Taipei）的警示數。"""
        boards_literal([board])
        since = {"board": board, "since": _datetime(now - timedelta(hours=24))}
        today = now.astimezone(TAIPEI).replace(hour=0, minute=0, second=0, microsecond=0)
        [counts] = self._client.query_rows(OVERVIEW_QUERY, {**since, "today": _datetime(today)})
        sentiments = {
            str(r["polarity"]): int(r["n"]) for r in self._client.query_rows(SENTIMENT_QUERY, since)
        }
        top = self._client.query_rows(
            CONTROVERSIAL_QUERY,
            {**since, "min_votes": str(CONTROVERSY_MIN_VOTES), "limit": str(OVERVIEW_TOP)},
        )
        ids = [str(r["post_id"]) for r in top]
        stats = self.post_stats(ids)
        return BoardOverview(
            board=board,
            posts_24h=int(counts["posts"]),
            comments_24h=int(counts["comments"]),
            sentiments=sentiments,
            top_controversial=[stats[p] for p in ids if p in stats],
            alerts_today=int(counts["alerts"]),
        )

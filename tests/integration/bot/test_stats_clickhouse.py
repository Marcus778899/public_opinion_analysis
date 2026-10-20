"""S6-04、S6-05：bot 的 ClickHouse 查詢在真的 ClickHouse 上的結果。"""

from datetime import UTC, datetime, timedelta

import pytest

from radar.bot.stats import ClickHouseQueries, PostSentiment
from radar.common.clickhouse import ClickHouseClient

PID = "Stock.M.1792000000.A.ABC"
PID2 = "Stock.M.1792000001.A.DEF"
GID = "Gossiping.M.1792000002.A.111"
NOW = datetime(2026, 10, 18, 3, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def ch(clickhouse):
    return clickhouse


@pytest.fixture
def queries(ch):
    for table in ("posts_latest", "comments_latest", "predictions", "alerts"):
        ch.execute(f"TRUNCATE TABLE {table}")
    return ClickHouseQueries(ch, hot_window_min=60, hot_limit=5)


def fmt(at: datetime) -> str:
    return at.strftime("%Y-%m-%d %H:%M:%S")


def add_post(ch: ClickHouseClient, post_id: str, title: str, created: datetime, lsn: int = 1):
    board = post_id.split(".", 1)[0]
    ch.execute(
        "INSERT INTO posts_latest (post_id, board, title, url, push_count, boo_count, created_at, "
        f"crawled_at, is_deleted, lsn) VALUES ('{post_id}', '{board}', '{title}', 'u', 0, 0, "
        f"'{fmt(created)}', '{fmt(created)}', false, {lsn})"
    )


def add_comments(
    ch: ClickHouseClient, post_id: str, types: list[str], at: datetime, deleted: int = 0
) -> None:
    board = post_id.split(".", 1)[0]
    rows = ",".join(
        f"('{post_id}', '{board}', {i}, '{t}', '{fmt(at)}', '{fmt(at)}', {i}, {deleted})"
        for i, t in enumerate(types, 1)
    )
    ch.execute(
        "INSERT INTO comments_latest (post_id, board, floor, type, commented_at, changed_at, lsn, "
        f"is_deleted) VALUES {rows}"
    )


def add_prediction(ch: ClickHouseClient, post_id: str, at: datetime, scores: dict[str, float]):
    polarity = max(scores, key=scores.__getitem__)
    pairs = ", ".join(f"'{k}', {v}" for k, v in scores.items())
    ch.execute(
        "INSERT INTO predictions (post_id, model_version, predicted_at, polarity, scores, "
        f"text_hash) VALUES ('{post_id}', 'm', '{fmt(at)}', '{polarity}', map({pairs}), '')"
    )


# --- post_stats ---


def test_post_stats_counts_types_and_takes_latest_prediction(ch, queries):
    add_post(ch, PID, "t", NOW)
    add_comments(ch, PID, ["push", "push", "boo", "arrow"], NOW)
    add_prediction(ch, PID, NOW - timedelta(minutes=5), {"negative": 0.9, "neutral": 0.1})
    add_prediction(ch, PID, NOW, {"positive": 0.7, "neutral": 0.3})

    [stats] = queries.post_stats([PID]).values()

    assert (stats.title, stats.push, stats.boo, stats.arrow) == ("t", 2, 1, 1)
    assert stats.sentiment == PostSentiment("positive", 0.7)


def test_post_stats_excludes_deleted_comments_and_handles_no_prediction(ch, queries):
    add_post(ch, PID, "t", NOW)
    add_comments(ch, PID, ["push"], NOW)
    add_comments(ch, PID2, ["boo"], NOW, deleted=1)
    add_post(ch, PID2, "t2", NOW)

    result = queries.post_stats([PID, PID2])

    assert (result[PID].push, result[PID].sentiment) == (1, None)
    assert (result[PID2].boo, result[PID2].push) == (0, 0)


def test_post_stats_unknown_post_not_returned(queries):
    assert queries.post_stats([PID]) == {}


# --- hot ---


def test_hot_orders_by_recent_comments_and_filters_boards(ch, queries):
    now = datetime.now(UTC)
    for post_id, n in ((PID, 3), (PID2, 5), (GID, 9)):
        add_post(ch, post_id, post_id, now)
        add_comments(ch, post_id, ["push"] * n, now)

    hot = queries.hot(["Stock"])

    assert [(h.stats.post_id, h.recent) for h in hot] == [(PID2, 5), (PID, 3)]
    assert queries.hot(None)[0].stats.post_id == GID


def test_hot_ignores_comments_outside_window(ch, queries):
    old = datetime.now(UTC) - timedelta(hours=2)
    add_post(ch, PID, "t", old)
    add_comments(ch, PID, ["push"] * 5, old)

    assert queries.hot(None) == []


# --- overview ---


def test_overview_counts_last_24h_sentiments_and_controversial(ch, queries):
    add_post(ch, PID, "爭議", NOW - timedelta(hours=2))
    add_comments(ch, PID, ["push"] * 6 + ["boo"] * 6, NOW - timedelta(hours=1))
    add_post(ch, PID2, "少", NOW - timedelta(hours=3))
    add_comments(ch, PID2, ["boo"] * 3, NOW - timedelta(hours=1))
    add_post(ch, "Stock.M.1791000000.A.OLD", "舊", NOW - timedelta(days=2))
    add_prediction(ch, PID, NOW, {"negative": 0.8, "neutral": 0.2})
    add_prediction(ch, PID2, NOW, {"neutral": 0.5, "negative": 0.5})

    overview = queries.overview("Stock", NOW)

    assert (overview.posts_24h, overview.comments_24h) == (2, 15)
    assert sum(overview.sentiments.values()) == 2
    assert [p.post_id for p in overview.top_controversial] == [PID]


def test_overview_alerts_today_uses_taipei_day(ch, queries):
    # 台北 10/18 00:00 = UTC 10/17 16:00
    for i, at in enumerate(("2026-10-17 15:59:00", "2026-10-17 16:01:00", "2026-10-18 02:00:00")):
        ch.execute(
            "INSERT INTO alerts (alert_id, unit_type, unit_key, board, window_start, window_end, "
            f"value, baseline, zscore, sample_post_ids, created_at) VALUES (generateUUIDv4(), "
            f"'board', 'Stock', 'Stock', '{at}', '{at}', {30 + i}, 1, 5, [], '{at}')"
        )

    assert queries.overview("Stock", NOW).alerts_today == 2

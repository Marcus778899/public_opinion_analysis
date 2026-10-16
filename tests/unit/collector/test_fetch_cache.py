from datetime import UTC, datetime, timedelta

from radar.collector.fetch_cache import RecentFetches

T0 = datetime(2026, 10, 9, 8, 0, tzinfo=UTC)
POST_ID = "Stock.M.1.A.001"


def test_unknown_post_not_fetched_since():
    assert not RecentFetches().fetched_since(POST_ID, T0)


def test_fetched_after_dispatch_returns_true():
    recent = RecentFetches()
    recent.remember(POST_ID, T0 + timedelta(seconds=1))

    assert recent.fetched_since(POST_ID, T0)


def test_fetched_before_dispatch_returns_false():
    recent = RecentFetches()
    recent.remember(POST_ID, T0 - timedelta(seconds=1))

    assert not recent.fetched_since(POST_ID, T0)


def test_fetched_at_same_time_as_dispatch_returns_false():
    recent = RecentFetches()
    recent.remember(POST_ID, T0)

    assert not recent.fetched_since(POST_ID, T0)


def test_remember_overwrites_with_latest_time():
    recent = RecentFetches()
    recent.remember(POST_ID, T0 - timedelta(minutes=5))
    recent.remember(POST_ID, T0 + timedelta(minutes=5))

    assert recent.fetched_since(POST_ID, T0)
    assert len(recent) == 1


def test_evicts_least_recently_remembered_when_full():
    recent = RecentFetches(max_size=2)
    later = T0 + timedelta(seconds=1)
    recent.remember("Stock.M.1.A.001", later)
    recent.remember("Stock.M.2.A.002", later)
    recent.remember("Stock.M.1.A.001", later)
    recent.remember("Stock.M.3.A.003", later)

    assert len(recent) == 2
    assert not recent.fetched_since("Stock.M.2.A.002", T0)
    assert recent.fetched_since("Stock.M.1.A.001", T0)
    assert recent.fetched_since("Stock.M.3.A.003", T0)

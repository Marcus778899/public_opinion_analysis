from datetime import UTC, datetime

from radar.collector.parsers.ptt import _bounded_comment_time

POST = datetime(2025, 10, 7, 4, 0, tzinfo=UTC)
CRAWL = datetime(2026, 10, 29, tzinfo=UTC)


def test_none_stays_none():
    assert _bounded_comment_time(None, POST, CRAWL) is None


def test_past_time_is_unchanged():
    t = datetime(2026, 3, 1, tzinfo=UTC)
    assert _bounded_comment_time(t, POST, CRAWL) == t


def test_future_time_steps_back_one_year_when_valid():
    # 文章 2025/10，推文 2026/11/05 > 爬取時間 → 2025/11/05
    got = _bounded_comment_time(datetime(2026, 11, 5, 2, tzinfo=UTC), POST, CRAWL)
    assert got == datetime(2025, 11, 5, 2, tzinfo=UTC)


def test_future_time_before_post_becomes_none():
    post = datetime(2026, 10, 20, tzinfo=UTC)
    assert _bounded_comment_time(datetime(2026, 11, 5, tzinfo=UTC), post, CRAWL) is None


def test_feb_29_cannot_step_back_becomes_none():
    crawl = datetime(2028, 1, 1, tzinfo=UTC)
    post = datetime(2027, 1, 1, tzinfo=UTC)
    assert _bounded_comment_time(datetime(2028, 2, 29, tzinfo=UTC), post, crawl) is None

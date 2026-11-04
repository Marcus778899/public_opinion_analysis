from datetime import UTC, datetime

from radar.collector.parsers.ptt import _bounded_comment_time

POST = datetime(2026, 10, 27, 0, 33, tzinfo=UTC)
CRAWL = datetime(2026, 10, 29, tzinfo=UTC)


def test_none_stays_none():
    assert _bounded_comment_time(None, POST, CRAWL) is None


def test_past_time_is_unchanged():
    t = datetime(2026, 10, 28, tzinfo=UTC)
    assert _bounded_comment_time(t, POST, CRAWL) == t


def test_next_year_future_comment_returns_to_post_year():
    # 文章 2026/10 帶入 05/01 的舊推文：parser 補成 2027/05/01，退回 2026/05/01
    got = _bounded_comment_time(datetime(2027, 5, 1, 1, 36, tzinfo=UTC), POST, CRAWL)
    assert got == datetime(2026, 5, 1, 1, 36, tzinfo=UTC)


def test_same_year_future_comment_becomes_none():
    # 11/05 月份不小於文章月份，parser 給 2026/11/05，無法判斷年份，回 None
    assert _bounded_comment_time(datetime(2026, 11, 5, tzinfo=UTC), POST, CRAWL) is None


def test_feb_29_cannot_step_back_becomes_none():
    post = datetime(2027, 10, 1, tzinfo=UTC)
    crawl = datetime(2027, 10, 5, tzinfo=UTC)
    assert _bounded_comment_time(datetime(2028, 2, 29, tzinfo=UTC), post, crawl) is None


def test_step_back_still_in_future_becomes_none():
    # 退一年後仍晚於爬取時間（文章標頭時間在未來）
    post = datetime(2026, 10, 27, tzinfo=UTC)
    crawl = datetime(2026, 1, 1, tzinfo=UTC)
    assert _bounded_comment_time(datetime(2027, 5, 1, tzinfo=UTC), post, crawl) is None

from datetime import UTC, datetime

import pytest

from radar.collector.parsers.ptt_time import (
    created_at_from_filename,
    parse_article_time,
    parse_comment_time,
)

# 2026-10-07 12:00 台北 = 04:00 UTC
POST_TIME = datetime(2026, 10, 7, 4, 0, tzinfo=UTC)
ARTICLE_UTC = datetime(2026, 10, 7, 3, 51, 41, tzinfo=UTC)


def test_parse_article_time_converts_taipei_to_utc():
    assert parse_article_time("Wed Oct 07 11:51:41 2026") == ARTICLE_UTC


def test_parse_article_time_handles_double_space_day():
    assert parse_article_time("Wed Oct  7 11:51:41 2026") == ARTICLE_UTC


@pytest.mark.parametrize(
    "text", ["", "Wed Foo 7 11:51:41 2026", "Wed Oct 7 25:00:00 2026", "garbage"]
)
def test_parse_article_time_returns_none_on_bad_format(text):
    assert parse_article_time(text) is None


def test_created_at_from_filename_uses_epoch():
    assert created_at_from_filename("M.1791345103.A.E41") == datetime.fromtimestamp(1791345103, UTC)


def test_created_at_from_filename_rejects_bad_name():
    with pytest.raises(ValueError):
        created_at_from_filename("index.html")


def test_parse_comment_time_uses_post_year():
    assert parse_comment_time(" 10/07 12:35", POST_TIME) == datetime(2026, 10, 7, 4, 35, tzinfo=UTC)


def test_parse_comment_time_strips_leading_ip():
    result = parse_comment_time("   192.0.2.1 10/07 12:35\n", POST_TIME)

    assert result == datetime(2026, 10, 7, 4, 35, tzinfo=UTC)


def test_parse_comment_time_cross_year_adds_one():
    post = datetime(2026, 12, 31, 15, 50, tzinfo=UTC)  # 台北 12/31 23:50

    assert parse_comment_time("01/01 00:05", post) == datetime(2026, 12, 31, 16, 5, tzinfo=UTC)


def test_parse_comment_time_year_based_on_taipei_not_utc():
    # UTC 仍是 12/31，但台北已是 2027/01/01；推文 01/01 不應再跨年到 2028
    post = datetime(2026, 12, 31, 16, 30, tzinfo=UTC)

    assert parse_comment_time("01/01 00:40", post) == datetime(2026, 12, 31, 16, 40, tzinfo=UTC)


@pytest.mark.parametrize("text", ["", "   ", "192.0.2.1"])
def test_parse_comment_time_returns_none_when_missing(text):
    assert parse_comment_time(text, POST_TIME) is None


def test_parse_comment_time_returns_none_on_invalid_date():
    assert parse_comment_time("02/30 12:00", POST_TIME) is None

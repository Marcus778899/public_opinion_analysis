import pytest

from radar.collector.parsers.ptt import (
    LIST_PUSH_BOOM,
    LIST_PUSH_XX,
    ListEntry,
    ParseError,
    parse_list_page,
    parse_list_push,
    post_id_from_url,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("", 0), (" 12 ", 12), ("爆", LIST_PUSH_BOOM), ("X3", -30), ("XX", LIST_PUSH_XX)],
)
def test_parse_list_push_known_formats(text, expected):
    assert parse_list_push(text) == expected


@pytest.mark.parametrize("text", ["?", "X", "1.5", "XXX"])
def test_parse_list_push_unknown_format_raises(text):
    with pytest.raises(ParseError):
        parse_list_push(text)


def test_list_page_excludes_pinned_posts_below_separator(fixture_html):
    page = parse_list_page(fixture_html("list_stock.html"), "Stock")

    assert len(page.entries) == 4
    assert all("公告" not in e.title for e in page.entries)


def test_list_page_entry_has_post_id_url_title_author(fixture_html):
    first = parse_list_page(fixture_html("list_stock.html"), "Stock").entries[0]

    assert first.post_id == "Stock.M.1791345103.A.E41"
    assert first.url == "https://www.ptt.cc/bbs/Stock/M.1791345103.A.E41.html"
    assert first.title == "[閒聊] 測試標題1"
    assert first.author == "user001"
    assert first.list_push == 10
    assert not first.is_deleted


def test_list_page_deleted_entry_has_no_post_id(fixture_html):
    deleted = parse_list_page(fixture_html("list_stock.html"), "Stock").entries[2]

    assert deleted.is_deleted
    assert (deleted.post_id, deleted.url, deleted.author) == (None, None, None)
    assert "本文已被刪除" in deleted.title


def test_list_page_x_count_is_negative(fixture_html):
    entry = parse_list_page(fixture_html("list_stock.html"), "Stock").entries[3]

    assert entry.list_push == -30
    assert not entry.is_boom


def test_list_entry_is_boom():
    assert ListEntry("Stock.M.1.A.1B2", "u", "t", "a", LIST_PUSH_BOOM, False).is_boom


def test_list_page_prev_page_url_is_absolute(fixture_html):
    page = parse_list_page(fixture_html("list_stock.html"), "Stock")

    assert page.prev_page_url == "https://www.ptt.cc/bbs/Stock/index10431.html"


def test_list_page_first_page_has_no_prev(fixture_html):
    page = parse_list_page(fixture_html("list_first_page.html"), "Stock")

    assert page.prev_page_url is None
    assert len(page.entries) == 20


def test_list_page_over18_raises_parse_error(fixture_html):
    with pytest.raises(ParseError, match="list container"):
        parse_list_page(fixture_html("over18.html"), "Gossiping")


def test_post_id_from_url():
    url = "https://www.ptt.cc/bbs/Tech_Job/M.1791345103.A.E41.html"

    assert post_id_from_url(url) == "Tech_Job.M.1791345103.A.E41"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.ptt.cc/bbs/Stock/index.html",
        "https://www.ptt.cc/bbs/Stock/M.1.A.1B2",
        "https://www.ptt.cc/man/Stock/M.1.A.1B2.html",
    ],
)
def test_post_id_from_url_rejects_non_post_path(url):
    with pytest.raises(ParseError):
        post_id_from_url(url)

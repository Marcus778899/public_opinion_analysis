import uuid
from datetime import UTC, datetime

import pytest

from radar.collector.parsers.ptt import ParseError, parse_post_page
from radar.common.enums import CommentType
from radar.common.schemas import RawPost

URL = "https://www.ptt.cc/bbs/Stock/M.1791345103.A.E41.html"
CRAWLED_AT = datetime(2026, 10, 7, 5, 0, tzinfo=UTC)
TASK_ID = uuid.uuid4()


def parse(html, url=URL, board="Stock"):
    return parse_post_page(html, board=board, url=url, crawled_at=CRAWLED_AT, task_id=TASK_ID)


def test_post_header_fields(fixture_html):
    post = parse(fixture_html("post_normal.html"))

    assert post.post_id == "Stock.M.1791345103.A.E41"
    assert post.author == "author1"
    assert post.title == "[新聞] 測試標題"
    assert post.created_at == datetime(2026, 10, 7, 3, 51, 41, tzinfo=UTC)
    assert (post.task_id, post.crawled_at, post.url) == (TASK_ID, CRAWLED_AT, URL)


def test_post_content_excludes_header_and_comments(fixture_html):
    content = parse(fixture_html("post_normal.html")).content

    assert content.startswith("測試內文第一行")
    assert "作者" not in content
    assert "測試推文" not in content


def test_post_content_stops_before_signature_footer(fixture_html):
    content = parse(fixture_html("post_normal.html")).content

    assert content.endswith("測試內文第二行。")
    assert "簽名檔" not in content
    assert "發信站" not in content


def test_post_comments_floor_type_user_content(fixture_html):
    comments = parse(fixture_html("post_normal.html")).comments

    assert [c.floor for c in comments] == list(range(1, 21))
    first = comments[0]
    assert (first.type, first.user_id, first.content) == (CommentType.PUSH, "user001", "測試推文1")
    assert first.commented_at == datetime(2026, 10, 7, 3, 53, tzinfo=UTC)
    assert {c.type for c in comments} == set(CommentType)


def test_post_counts_computed_from_comments(fixture_html):
    post = parse(fixture_html("post_normal.html"))

    assert (post.push_count, post.boo_count) == (9, 2)


def test_post_boom_has_over_100_pushes_and_skips_warning_box(fixture_html):
    post = parse(
        fixture_html("post_boom.html"), url="https://www.ptt.cc/bbs/Stock/M.1791333003.A.7A2.html"
    )

    assert post.push_count == 140
    assert len(post.comments) == 190
    assert post.comments[-1].floor == 190


def test_post_comment_with_ip_parses_time(fixture_html):
    post = parse(
        fixture_html("post_ip_comments.html"),
        url="https://www.ptt.cc/bbs/Gossiping/M.1791346094.A.372.html",
        board="Gossiping",
    )

    assert len(post.comments) == 55
    assert all(c.commented_at is not None for c in post.comments)
    assert (post.push_count, post.boo_count) == (12, 5)


def test_post_cross_year_comment_time(fixture_html):
    comments = parse(fixture_html("post_cross_year.html")).comments

    assert comments[0].commented_at == datetime(2026, 12, 31, 15, 55, tzinfo=UTC)
    assert comments[-1].commented_at == datetime(2026, 12, 31, 16, 5, tzinfo=UTC)


def test_post_edited_article_keeps_edit_lines_out_of_comments(fixture_html):
    post = parse(fixture_html("post_edited.html"))

    assert len(post.comments) == 20
    assert all("編輯" not in (c.content or "") for c in post.comments)
    assert "編輯" not in post.content


def test_post_missing_header_falls_back_to_filename_time(fixture_html):
    post = parse(fixture_html("post_no_header.html"))

    assert post.created_at == datetime.fromtimestamp(1791345103, UTC)
    assert (post.author, post.title) == (None, None)
    assert post.content.startswith("測試內文第一行")


def test_post_over18_page_raises_parse_error(fixture_html):
    with pytest.raises(ParseError, match="main-content"):
        parse(fixture_html("over18.html"))


def test_post_bad_url_raises_parse_error(fixture_html):
    with pytest.raises(ParseError):
        parse(fixture_html("post_normal.html"), url="https://www.ptt.cc/bbs/Stock/index.html")


def test_post_result_is_valid_raw_post(fixture_html):
    post = parse(fixture_html("post_normal.html"))

    assert RawPost.model_validate_json(post.model_dump_json()) == post

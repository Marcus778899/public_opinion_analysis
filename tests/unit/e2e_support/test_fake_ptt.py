import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from radar.collector.parsers.ptt import parse_list_page, parse_post_page
from tests.e2e.fake_ptt import FakePtt, NewComments, NewPost, create_app


@pytest.fixture
def ptt():
    return FakePtt()


@pytest.fixture
def client(ptt):
    return TestClient(create_app(ptt))


def parse_post(ptt, post):
    return parse_post_page(
        ptt.render_post(post.board, post.filename),
        board=post.board,
        url=f"https://www.ptt.cc{post.path}",
        crawled_at=datetime.now(UTC),
        task_id=uuid.uuid4(),
    )


def test_list_page_parses_with_real_parser(ptt):
    first = ptt.add_post(NewPost(board="E2E", title="[測試] <b>標題</b>"))
    ptt.add_post(NewPost(board="Other", title="別的看板"))

    page = parse_list_page(ptt.render_list("E2E"), "E2E")

    assert [e.post_id for e in page.entries] == [first.post_id]
    assert page.entries[0].title == "[測試] <b>標題</b>"
    assert page.prev_page_url is None


def test_post_page_parses_with_real_parser(ptt):
    post = ptt.add_post(NewPost(board="E2E", title="[測試] 標題", content="第一行"))

    parsed = parse_post(ptt, post)

    assert (parsed.post_id, parsed.title, parsed.content) == (post.post_id, "[測試] 標題", "第一行")
    assert parsed.created_at == post.created_at


def test_added_comments_change_counts(ptt):
    post = ptt.add_post(NewPost(board="E2E", title="t"))

    ptt.add_comments(post.post_id, NewComments(pushes=12, boos=1))

    parsed = parse_post(ptt, post)
    assert (parsed.push_count, parsed.boo_count) == (12, 1)
    assert all(c.commented_at is not None for c in parsed.comments)
    assert parse_list_page(ptt.render_list("E2E"), "E2E").entries[0].list_push == 11


def test_deleted_post_returns_404_and_list_shows_deleted(ptt, client):
    post = ptt.add_post(NewPost(board="E2E", title="t"))

    assert client.delete(f"/_control/posts/{post.post_id}").status_code == 204

    assert client.get(post.path).status_code == 404
    [entry] = parse_list_page(client.get("/bbs/E2E/index.html").text, "E2E").entries
    assert entry.is_deleted


def test_filenames_unique_within_same_second(ptt):
    posts = [ptt.add_post(NewPost(board="E2E", title=str(i))) for i in range(50)]

    assert len({p.post_id for p in posts}) == 50


def test_control_endpoints(client):
    created = client.post("/_control/posts", json={"board": "E2E", "title": "t"}).json()

    comments = client.post(f"/_control/posts/{created['post_id']}/comments", json={"pushes": 2})

    assert comments.json() == {"comments": 2}
    assert client.post("/_control/posts/E2E.M.1.A.001/comments", json={}).status_code == 404
    assert client.post("/_control/reset").status_code == 204
    assert parse_list_page(client.get("/bbs/E2E/index.html").text, "E2E").entries == []

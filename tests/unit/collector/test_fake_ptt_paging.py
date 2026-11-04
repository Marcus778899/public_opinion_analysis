"""假 PTT 的列表分頁（e2e 補抓測試用）。"""

from fastapi.testclient import TestClient

from tests.e2e.fake_ptt import FakePtt, NewPost, create_app


def populated(n: int, size: int) -> tuple[FakePtt, TestClient]:
    state = FakePtt()
    for i in range(n):
        state.add_post(NewPost(board="B", title=f"t{i}"))
    state.page_sizes["B"] = size
    return state, TestClient(create_app(state))


def test_latest_page_links_to_previous_page():
    _, client = populated(5, 2)

    body = client.get("/bbs/B/index.html").text

    assert 'href="/bbs/B/index2.html">&lsaquo;' in body
    assert body.count('class="r-ent"') == 1


def test_numbered_page_shows_its_slice_and_first_page_has_no_prev():
    _, client = populated(5, 2)

    first = client.get("/bbs/B/index1.html").text
    middle = client.get("/bbs/B/index2.html").text

    assert first.count('class="r-ent"') == 2
    assert "index0.html" not in first
    assert 'href="/bbs/B/index1.html">&lsaquo;' in middle


def test_default_page_size_keeps_small_boards_on_one_page():
    _, client = populated(3, 20)

    body = client.get("/bbs/B/index.html").text

    assert body.count('class="r-ent"') == 3
    assert 'class="btn wide disabled">&lsaquo;' in body


def test_page_size_control_endpoint_and_reset():
    state, client = populated(4, 20)

    assert client.put("/_control/boards/B/page_size", json={"size": 2}).status_code == 204
    assert state.page_sizes["B"] == 2
    assert client.put("/_control/boards/B/page_size", json={"size": 0}).status_code == 422
    client.post("/_control/reset")
    assert state.page_sizes == {}

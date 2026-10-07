import io
import json
import urllib.error

import pytest

from radar.api import seed as seed_module
from radar.api.seed import INITIAL_BOARDS, seed


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def http(monkeypatch):
    """依看板名稱回傳指定狀態碼；記錄每次送出的 request。"""
    responses: dict[str, int] = {}
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        board = json.loads(request.data)["board"]
        code = responses.get(board, 201)
        if code >= 400:
            raise urllib.error.HTTPError(request.full_url, code, "err", {}, io.BytesIO(b""))
        return FakeResponse()

    monkeypatch.setattr(seed_module.urllib.request, "urlopen", fake_urlopen)
    return responses, requests


def test_seed_creates_missing_boards(http):
    _, requests = http

    result = seed("http://api:8000/", INITIAL_BOARDS)

    assert result.created == ["Gossiping", "Stock", "Tech_Job"]
    assert requests[0].full_url == "http://api:8000/boards"
    assert requests[0].get_method() == "POST"


def test_seed_skips_existing_boards_on_409(http):
    responses, _ = http
    responses["Stock"] = 409

    result = seed("http://api:8000", INITIAL_BOARDS)

    assert result.skipped == ["Stock"]
    assert result.created == ["Gossiping", "Tech_Job"]


def test_seed_raises_on_other_errors(http):
    responses, _ = http
    responses["Gossiping"] = 500

    with pytest.raises(urllib.error.HTTPError):
        seed("http://api:8000", INITIAL_BOARDS)


def test_seed_rejects_non_http_url():
    with pytest.raises(ValueError):
        seed("file:///etc/passwd", INITIAL_BOARDS)


def test_initial_boards_match_spec():
    assert {b["board"]: (b["interval_sec"], b["recrawl_min_push"]) for b in INITIAL_BOARDS} == {
        "Gossiping": (60, 10),
        "Stock": (120, 0),
        "Tech_Job": (600, 0),
    }

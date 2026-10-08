import httpx2
import pytest

from radar.collector.http import OVER18_COOKIE, USER_AGENT, FetchError, PttClient
from radar.common.kafka.consumer import TransientError

URL = "https://www.ptt.cc/bbs/Stock/index.html"


class CountingLimiter:
    def __init__(self) -> None:
        self.calls = 0

    def wait(self) -> float:
        self.calls += 1
        return 0.0


def client_with(handler):
    return PttClient(CountingLimiter(), transport=httpx2.MockTransport(handler))


def test_fetch_sends_over18_cookie_and_user_agent():
    seen = {}

    def handler(request):
        seen["ua"] = request.headers["user-agent"]
        seen["cookie"] = request.headers.get("cookie", "")
        return httpx2.Response(200, text="<html>ok</html>")

    result = client_with(handler).fetch(URL)

    assert (result.status, result.html, result.url) == (200, "<html>ok</html>", URL)
    assert seen["ua"] == USER_AGENT
    assert "over18=1" in seen["cookie"] and OVER18_COOKIE == {"over18": "1"}


def test_fetch_waits_on_rate_limiter():
    limiter = CountingLimiter()
    client = PttClient(limiter, transport=httpx2.MockTransport(lambda r: httpx2.Response(200)))

    client.fetch(URL)
    client.fetch(URL)

    assert limiter.calls == 2


def test_fetch_returns_404_without_raising():
    result = client_with(lambda r: httpx2.Response(404, text="not found")).fetch(URL)

    assert result.status == 404


@pytest.mark.parametrize("status", [429, 500, 502, 503])
def test_fetch_retryable_status_raises_transient(status):
    with pytest.raises(TransientError):
        client_with(lambda r: httpx2.Response(status)).fetch(URL)


@pytest.mark.parametrize("status", [302, 403])
def test_fetch_other_status_raises_fetch_error(status):
    with pytest.raises(FetchError):
        client_with(lambda r: httpx2.Response(status)).fetch(URL)


def test_fetch_timeout_raises_transient():
    def handler(request):
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(TransientError):
        client_with(handler).fetch(URL)


def test_base_url_override_rewrites_host_but_keeps_result_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx2.Response(200, text="ok")

    client = PttClient(
        CountingLimiter(),
        transport=httpx2.MockTransport(handler),
        base_url_override="http://fake-ptt:8080/",
    )

    result = client.fetch(URL)

    assert seen["url"] == "http://fake-ptt:8080/bbs/Stock/index.html"
    assert result.url == URL


def test_no_override_requests_original_url():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx2.Response(200)

    client_with(handler).fetch(URL)

    assert seen["url"] == URL

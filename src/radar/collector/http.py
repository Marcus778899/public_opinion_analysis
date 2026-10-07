"""對 PTT 發請求；帶 over18 cookie、固定 User-Agent，並經過 RateLimiter（開發規格 8.1）。"""

from dataclasses import dataclass
from typing import Protocol

import httpx2

from radar.common.ids import PTT_BASE_URL
from radar.common.kafka.consumer import TransientError
from radar.common.rate_limit import RateLimiter

USER_AGENT = "radar-crawler/0.1 (+https://github.com/Marcus778899/public_opinion_analysis)"
OVER18_COOKIE = {"over18": "1"}
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class FetchResult:
    url: str
    status: int
    html: str


class FetchError(Exception):
    """不可重試的回應（403、3xx 等）；爬蟲記錄後略過該任務。"""


class PttFetcher(Protocol):
    """爬蟲只依賴這個介面；單元測試以讀 fixture 的 fake 實作取代。"""

    def fetch(self, url: str) -> FetchResult: ...


class PttClient:
    def __init__(
        self,
        limiter: RateLimiter,
        *,
        timeout_s: float = 10.0,
        transport: httpx2.BaseTransport | None = None,
        base_url_override: str | None = None,
    ) -> None:
        # NOTE: transport 可注入，單元測試用 MockTransport，不對 PTT 發請求
        # NOTE: base_url_override 只給端到端測試，把 www.ptt.cc 換成假 PTT 伺服器
        self._limiter = limiter
        self._base_url_override = base_url_override
        self._client = httpx2.Client(
            headers={"User-Agent": USER_AGENT},
            cookies=OVER18_COOKIE,
            timeout=timeout_s,
            follow_redirects=False,
            transport=transport,
        )

    def fetch(self, url: str) -> FetchResult:
        """200 與 404 正常回傳；5xx、429、逾時、連線錯誤拋 TransientError。"""
        self._limiter.wait()
        try:
            response = self._client.get(self._rewrite(url))
        except httpx2.TransportError as e:
            raise TransientError(f"GET {url} failed: {e!r}") from e
        status = response.status_code
        if status in (200, 404):
            return FetchResult(url=url, status=status, html=response.text)
        if status in _RETRYABLE_STATUS:
            raise TransientError(f"GET {url} returned {status}")
        raise FetchError(f"GET {url} returned {status}")

    def close(self) -> None:
        self._client.close()

    def _rewrite(self, url: str) -> str:
        """只換掉開頭的 PTT_BASE_URL；FetchResult.url 仍是原網址，parser 才算得出正確的 post_id。"""
        if self._base_url_override and url.startswith(PTT_BASE_URL):
            return self._base_url_override.rstrip("/") + url[len(PTT_BASE_URL) :]
        return url

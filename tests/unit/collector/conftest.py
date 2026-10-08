from pathlib import Path

import pytest

from radar.collector.http import FetchResult

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "ptt"
INDEX_URL = "https://www.ptt.cc/bbs/Stock/index.html"
PREV_URL = "https://www.ptt.cc/bbs/Stock/index10431.html"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeFetcher:
    """依網址回傳 fixture；沒指定的文章頁一律回 post_normal.html。"""

    def __init__(self) -> None:
        self.pages = {INDEX_URL: read_fixture("list_stock.html")}
        self.status: dict[str, int] = {}
        self.errors: dict[str, Exception] = {}
        self.default_post_html = read_fixture("post_normal.html")
        self.requested: list[str] = []

    def fetch(self, url: str) -> FetchResult:
        self.requested.append(url)
        if url in self.errors:
            raise self.errors[url]
        html = self.pages.get(url)
        if html is None and "/M." in url:
            html = self.default_post_html
        status = self.status.get(url, 200 if html is not None else 404)
        return FetchResult(url=url, status=status, html=html or "")

    def post_requests(self) -> list[str]:
        return [u for u in self.requested if "/M." in u]

    def list_requests(self) -> list[str]:
        return [u for u in self.requested if "/index" in u]


@pytest.fixture
def fetcher() -> FakeFetcher:
    return FakeFetcher()

"""ml 單元測試共用的替身。"""

from radar.common.schemas import Sentiment
from radar.ml.labeling.prompt import PostText


class FakeClickHouse:
    """query_rows 依序回傳 results；記錄收到的 SQL 與參數。"""

    def __init__(self, *results: list[dict]) -> None:
        self._results = list(results)
        self.queries: list[tuple[str, dict[str, str] | None]] = []

    def query_rows(self, sql: str, params: dict[str, str] | None = None) -> list[dict]:
        self.queries.append((sql, params))
        return self._results.pop(0) if self._results else []

    def close(self) -> None:
        pass


class ScriptedLabeler:
    """依序拋出或回傳 script 中的項目；Exception 會被拋出。"""

    def __init__(self, *script: list[Sentiment] | Exception, name: str = "fake") -> None:
        self._script = list(script)
        self._name = name
        self.calls: list[PostText] = []

    @property
    def name(self) -> str:
        return self._name

    def label(self, post: PostText) -> list[Sentiment]:
        self.calls.append(post)
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self) -> None:
        pass


def post(post_id: str = "Stock.M.1759730000.A.1B2", board: str = "Stock") -> PostText:
    return PostText(post_id, board, "標題", "內文")


def row(post_id: str, board: str = "Stock") -> dict:
    return {"post_id": post_id, "board": board, "title": "t", "content": "c"}

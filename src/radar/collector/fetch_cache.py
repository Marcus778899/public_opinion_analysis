"""開發規格 7.12：記住各文章最後一次抓內頁的時間，略過派發後已抓過的重複任務。"""

from collections import OrderedDict
from datetime import datetime


class RecentFetches:
    """LRU；重啟或 rebalance 後清空只會多抓幾次，結果仍正確。"""

    def __init__(self, max_size: int = 20_000) -> None:
        self._max_size = max_size
        self._data: OrderedDict[str, datetime] = OrderedDict()

    def fetched_since(self, post_id: str, dispatched_at: datetime) -> bool:
        """dispatched_at 之後已抓過 → True（任務是重複的）。"""
        fetched_at = self._data.get(post_id)
        return fetched_at is not None and fetched_at > dispatched_at

    def remember(self, post_id: str, fetched_at: datetime) -> None:
        self._data[post_id] = fetched_at
        self._data.move_to_end(post_id)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)

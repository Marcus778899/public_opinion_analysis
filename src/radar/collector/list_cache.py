"""開發規格 7.1：記住列表頁上各文章的推文數，沒變就不抓內頁。"""

from collections import OrderedDict

from radar.collector.parsers.ptt import ListEntry


class ListPushCache:
    """LRU；重啟或 rebalance 後清空只會多抓幾次內頁，結果仍正確。"""

    def __init__(self, max_size: int = 20_000) -> None:
        self._max_size = max_size
        self._data: OrderedDict[str, int] = OrderedDict()

    def should_fetch(self, entry: ListEntry) -> bool:
        """沒見過、或推文數變了 → True。

        爆文的數字固定是 100，所以「爆 → 爆」視為沒變，交給 dispatch_due_posts 重爬；
        「99 → 爆」仍算變化，會抓一次。
        """
        if entry.post_id is None:
            return False
        return self._data.get(entry.post_id) != entry.list_push

    def remember(self, entry: ListEntry) -> None:
        if entry.post_id is None:
            return
        self._data[entry.post_id] = entry.list_push
        self._data.move_to_end(entry.post_id)
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

    def __contains__(self, post_id: object) -> bool:
        return post_id in self._data

    def __len__(self) -> int:
        return len(self._data)

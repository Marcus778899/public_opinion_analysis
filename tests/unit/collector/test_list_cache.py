from radar.collector.list_cache import ListPushCache
from radar.collector.parsers.ptt import LIST_PUSH_BOOM, ListEntry


def entry(post_id="Stock.M.1.A.001", push=3):
    url = f"https://www.ptt.cc/bbs/Stock/{post_id.split('.', 1)[1]}.html" if post_id else None
    return ListEntry(post_id, url, "t", "a", push, post_id is None)


def test_unseen_entry_should_fetch():
    assert ListPushCache().should_fetch(entry())


def test_same_push_count_should_not_fetch():
    cache = ListPushCache()
    cache.remember(entry(push=3))

    assert not cache.should_fetch(entry(push=3))


def test_changed_push_count_should_fetch():
    cache = ListPushCache()
    cache.remember(entry(push=3))

    assert cache.should_fetch(entry(push=4))


def test_deleted_entry_never_fetched():
    cache = ListPushCache()
    deleted = entry(post_id=None)
    cache.remember(deleted)

    assert not cache.should_fetch(deleted)
    assert len(cache) == 0


def test_seen_boom_entry_not_fetched():
    cache = ListPushCache()
    cache.remember(entry(push=LIST_PUSH_BOOM))

    assert not cache.should_fetch(entry(push=LIST_PUSH_BOOM))


def test_unseen_boom_entry_fetched_once():
    cache = ListPushCache()
    cache.remember(entry(push=99))

    assert cache.should_fetch(entry(push=LIST_PUSH_BOOM))


def test_evicts_oldest_when_full():
    cache = ListPushCache(max_size=2)
    cache.remember(entry("Stock.M.1.A.001"))
    cache.remember(entry("Stock.M.2.A.002"))
    cache.remember(entry("Stock.M.1.A.001"))  # 重新使用，變成最新
    cache.remember(entry("Stock.M.3.A.003"))

    assert "Stock.M.2.A.002" not in cache
    assert "Stock.M.1.A.001" in cache
    assert len(cache) == 2

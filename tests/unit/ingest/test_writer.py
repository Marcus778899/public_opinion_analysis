from datetime import timedelta

from radar.ingest.writer import dedupe_posts
from tests.helpers.raw_posts import T0, make_post


def test_dedupe_keeps_latest_crawled_at():
    old = make_post(crawled_at=T0, n_push=1)
    new = make_post(crawled_at=T0 + timedelta(minutes=2), n_push=5)

    assert dedupe_posts([new, old]) == [new]
    assert dedupe_posts([old, new]) == [new]


def test_dedupe_preserves_order_of_first_appearance():
    a = make_post("Stock.M.1.A.001")
    b = make_post("Stock.M.2.A.002")
    a_newer = make_post("Stock.M.1.A.001", crawled_at=T0 + timedelta(minutes=1))

    assert [p.post_id for p in dedupe_posts([a, b, a_newer])] == [a.post_id, b.post_id]


def test_dedupe_empty_batch():
    assert dedupe_posts([]) == []

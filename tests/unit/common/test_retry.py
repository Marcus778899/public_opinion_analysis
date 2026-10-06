from itertools import islice

from radar.common.retry import backoff_delays


def test_backoff_delays_grow_by_factor():
    assert list(islice(backoff_delays(base_s=1, factor=2, max_s=100), 4)) == [1, 2, 4, 8]


def test_backoff_delays_capped_at_max():
    assert list(islice(backoff_delays(base_s=1, factor=10, max_s=5), 4)) == [1, 5, 5, 5]


def test_backoff_delays_base_above_max_is_capped():
    assert next(backoff_delays(base_s=60, max_s=30)) == 30

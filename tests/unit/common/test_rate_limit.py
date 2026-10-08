from radar.common.rate_limit import RateLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def make(rand_value=0.5):
    clock = FakeClock()
    limiter = RateLimiter(2.0, 2.0, clock=clock, sleep=clock.sleep, rand=lambda: rand_value)
    return limiter, clock


def test_first_call_does_not_wait():
    limiter, clock = make()

    assert limiter.wait() == 0.0
    assert clock.slept == []


def test_waits_remaining_interval_plus_jitter():
    limiter, clock = make(rand_value=0.5)
    limiter.wait()
    clock.now += 1.0

    assert limiter.wait() == 2.0  # 2 秒間隔 + 1 秒 jitter - 已過 1 秒
    assert clock.slept == [2.0]


def test_no_wait_when_interval_already_passed():
    limiter, clock = make()
    limiter.wait()
    clock.now += 10

    assert limiter.wait() == 0.0


def test_jitter_within_range():
    for rand_value, expected in [(0.0, 2.0), (0.999, 3.998)]:
        limiter, _ = make(rand_value)
        limiter.wait()

        assert round(limiter.wait(), 3) == expected

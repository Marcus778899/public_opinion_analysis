"""請求速率限制：兩次請求至少間隔 min_interval_s，再加 0～jitter_s 的隨機秒數。"""

import random
import time
from collections.abc import Callable


class RateLimiter:
    def __init__(
        self,
        min_interval_s: float = 2.0,
        jitter_s: float = 2.0,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rand: Callable[[], float] = random.random,
    ) -> None:
        # NOTE: 平均約 3 秒一次；3 個爬蟲合計約 1 次/秒，符合 S1 驗收上限
        self._min_interval_s = min_interval_s
        self._jitter_s = jitter_s
        self._clock = clock
        self._sleep = sleep
        self._rand = rand
        self._next_allowed: float | None = None

    def wait(self) -> float:
        """必要時 sleep，回傳實際等待的秒數。"""
        delay = 0.0
        if self._next_allowed is not None:
            delay = max(0.0, self._next_allowed - self._clock())
        if delay > 0:
            self._sleep(delay)
        jitter = self._jitter_s * self._rand()
        self._next_allowed = self._clock() + self._min_interval_s + jitter
        return delay

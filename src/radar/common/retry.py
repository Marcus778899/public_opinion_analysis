from collections.abc import Iterator


def backoff_delays(
    base_s: float = 0.5, factor: float = 2.0, max_s: float = 30.0
) -> Iterator[float]:
    """無限產生指數退避秒數，上限 max_s；暫時性錯誤重試用。"""
    delay = base_s
    while True:
        yield min(delay, max_s)
        delay = min(delay * factor, max_s)

"""依服務商名稱建立 Labeler；設定從各服務商的環境變數讀（開發規格 7.11）。"""

from collections.abc import Callable

from radar.common.rate_limit import RateLimiter
from radar.common.settings import GeminiSettings, GroqSettings, OpenRouterSettings
from radar.ml.labeling.llm import GeminiLabeler, Labeler, OpenAICompatibleLabeler


def _gemini(max_chars: int) -> Labeler:
    s = GeminiSettings()
    return GeminiLabeler(s.model, s, RateLimiter(s.min_interval_s, 0.5), max_chars)


def _groq(max_chars: int) -> Labeler:
    s = GroqSettings()
    key = s.api_key.get_secret_value()
    limiter = RateLimiter(s.min_interval_s, 0.5)
    return OpenAICompatibleLabeler("groq", s.model, s.base_url, key, limiter, max_chars)


def _openrouter(max_chars: int) -> Labeler:
    s = OpenRouterSettings()
    key = s.api_key.get_secret_value()
    limiter = RateLimiter(s.min_interval_s, 0.5)
    return OpenAICompatibleLabeler("openrouter", s.model, s.base_url, key, limiter, max_chars)


PROVIDERS: dict[str, Callable[[int], Labeler]] = {
    "gemini": _gemini,
    "groq": _groq,
    "openrouter": _openrouter,
}


def build_labeler(provider: str, max_chars: int) -> Labeler:
    try:
        factory = PROVIDERS[provider]
    except KeyError:
        expected = sorted(PROVIDERS)
        raise ValueError(f"unknown labeler provider {provider!r}; expected {expected}") from None
    return factory(max_chars)

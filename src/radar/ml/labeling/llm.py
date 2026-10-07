"""LLM 標註者（開發規格 7.11）；換付費 API 時新增一個實作 Labeler 的類別即可。"""

import time
from collections.abc import Callable
from typing import Any, Protocol

import httpx2

from radar.common.log import log
from radar.common.rate_limit import RateLimiter
from radar.common.schemas import Sentiment
from radar.common.settings import GeminiSettings
from radar.ml.labeling.prompt import (
    JSON_SCHEMA,
    RESPONSE_SCHEMA,
    LabelParseError,
    PostText,
    build_prompt,
    parse_sentiments,
)


class LabelerError(Exception):
    """不可重試：被安全機制擋下、輸出不合法等；記錄後略過該篇。"""


class RetryableLabelerError(Exception):
    """可重試：429（每分鐘額度）、5xx、連線錯誤。"""


class QuotaExhaustedError(Exception):
    """每日額度用完；backfill 應停止，隔天再續跑。"""


class LabelerOutputError(LabelerError):
    """輸出不符合格式；同一篇重送一次常會改善（temperature=0 仍非完全決定性）。"""


OUTPUT_RETRIES = 1


class LabelerSetupError(RuntimeError):
    """API key、模型名稱或請求格式錯誤；每篇都會失敗，應直接中止。"""


class Labeler(Protocol):
    @property
    def name(self) -> str:
        """寫入 Label.labeler 的值，例如模型名稱。"""
        ...

    def label(self, post: PostText) -> list[Sentiment]: ...

    def close(self) -> None: ...


class GeminiLabeler:
    def __init__(
        self,
        model: str,
        settings: GeminiSettings,
        limiter: RateLimiter,
        max_chars: int,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._limiter = limiter
        self._max_chars = max_chars
        # NOTE: key 放 header 而非 query string，避免出現在錯誤訊息與 log 的 URL 裡
        self._client = httpx2.Client(
            base_url=settings.base_url,
            headers={"x-goog-api-key": settings.api_key.get_secret_value()},
            transport=transport,
            timeout=60.0,
        )

    @property
    def name(self) -> str:
        return self._model

    def label(self, post: PostText) -> list[Sentiment]:
        return _with_output_retry(lambda: self._label_once(post))

    def _label_once(self, post: PostText) -> list[Sentiment]:
        self._limiter.wait()
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": build_prompt(post, self._max_chars)}]}
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
            },
        }
        try:
            resp = self._client.post(f"/v1beta/models/{self._model}:generateContent", json=body)
        except httpx2.TransportError as e:
            raise RetryableLabelerError(f"{post.post_id}: {e!r}") from e
        if resp.status_code == 429:
            if _is_daily_quota(resp):
                raise QuotaExhaustedError(f"{self._model}: daily quota exhausted")
            raise RetryableLabelerError(f"{post.post_id}: rate limited")
        if resp.status_code >= 500:
            raise RetryableLabelerError(f"{post.post_id}: {resp.status_code}")
        if resp.status_code != 200:
            # 400/401/403/404 代表設定或請求格式有誤，每篇都會失敗，不該逐篇略過
            raise LabelerSetupError(f"{self._model}: {resp.status_code} {resp.text[:300]}")
        return self._parse(post.post_id, resp.json())

    def _parse(self, post_id: str, data: dict[str, Any]) -> list[Sentiment]:
        blocked = data.get("promptFeedback", {}).get("blockReason")
        if blocked:
            raise LabelerError(f"{post_id}: prompt blocked ({blocked})")
        candidates = data.get("candidates") or []
        if not candidates:
            raise LabelerError(f"{post_id}: no candidates")
        candidate = candidates[0]
        parts = candidate.get("content", {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        if not text:
            raise LabelerError(f"{post_id}: empty output ({candidate.get('finishReason')})")
        try:
            return parse_sentiments(text)
        except LabelParseError as e:
            raise LabelerOutputError(f"{post_id}: {e}") from e

    def close(self) -> None:
        self._client.close()


def _is_daily_quota(resp: httpx2.Response) -> bool:
    """429 的 QuotaFailure 帶 quotaId；含 PerDay 代表每日額度用完，其餘視為每分鐘額度。"""
    try:
        details = resp.json()["error"].get("details", [])
    except (ValueError, KeyError, AttributeError):
        return False
    quota_ids = [
        v.get("quotaId", "")
        for d in details
        if isinstance(d, dict)
        for v in d.get("violations", [])
        if isinstance(v, dict)
    ]
    return any("PerDay" in q for q in quota_ids)


class OpenAICompatibleLabeler:
    """Groq、OpenRouter 等 OpenAI 相容的 chat completions API（開發規格 7.11）。"""

    def __init__(
        self,
        provider: str,
        model: str,
        base_url: str,
        api_key: str,
        limiter: RateLimiter,
        max_chars: int,
        transport: httpx2.BaseTransport | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._limiter = limiter
        self._max_chars = max_chars
        self._client = httpx2.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            transport=transport,
            timeout=60.0,
        )

    @property
    def name(self) -> str:
        return f"{self._provider}:{self._model}"

    def label(self, post: PostText) -> list[Sentiment]:
        return _with_output_retry(lambda: self._label_once(post))

    def _label_once(self, post: PostText) -> list[Sentiment]:
        self._limiter.wait()
        body = {
            "model": self._model,
            "messages": [{"role": "user", "content": build_prompt(post, self._max_chars)}],
            "temperature": 0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "sentiments", "strict": True, "schema": JSON_SCHEMA},
            },
        }
        try:
            resp = self._client.post("/chat/completions", json=body)
        except httpx2.TransportError as e:
            raise RetryableLabelerError(f"{post.post_id}: {e!r}") from e
        if resp.status_code == 429:
            if _mentions_daily_limit(resp.text):
                raise QuotaExhaustedError(f"{self.name}: daily quota exhausted")
            raise RetryableLabelerError(f"{post.post_id}: rate limited")
        if resp.status_code >= 500:
            raise RetryableLabelerError(f"{post.post_id}: {resp.status_code}")
        if resp.status_code != 200:
            raise LabelerSetupError(f"{self.name}: {resp.status_code} {resp.text[:300]}")
        return self._parse(post.post_id, resp.json())

    def _parse(self, post_id: str, data: dict[str, Any]) -> list[Sentiment]:
        # NOTE: OpenRouter 上游出錯時仍回 200，錯誤放在 body 的 error 欄位
        if data.get("error"):
            raise RetryableLabelerError(f"{post_id}: upstream error {data['error']}")
        choices = data.get("choices") or []
        if not choices:
            raise LabelerError(f"{post_id}: no choices")
        choice = choices[0]
        text = (choice.get("message") or {}).get("content") or ""
        if not text:
            raise LabelerError(f"{post_id}: empty output ({choice.get('finish_reason')})")
        try:
            return parse_sentiments(text)
        except LabelParseError as e:
            raise LabelerOutputError(f"{post_id}: {e}") from e

    def close(self) -> None:
        self._client.close()


def _mentions_daily_limit(body: str) -> bool:
    """429 是否為每日額度用完；Groq 與 OpenRouter 的錯誤訊息都會提到 per day。"""
    lowered = body.lower()
    return any(k in lowered for k in ("per day", "per-day", "(rpd)", "daily"))


def _with_output_retry(call: Callable[[], list[Sentiment]]) -> list[Sentiment]:
    for attempt in range(OUTPUT_RETRIES + 1):
        try:
            return call()
        except LabelerOutputError:
            if attempt == OUTPUT_RETRIES:
                raise
    raise AssertionError("unreachable")


class AllExhaustedError(RetryableLabelerError):
    """所有標註者的每日額度都用完；串流標註稍後重試，不丟訊息。"""


class FallbackLabeler:
    """依序嘗試多個標註者；每日額度用完的暫停 cooldown 秒再試（開發規格 7.11，只用於串流）。"""

    def __init__(
        self,
        labelers: list[Labeler],
        cooldown_s: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not labelers:
            raise ValueError("FallbackLabeler needs at least one labeler")
        self._labelers = labelers
        self._cooldown_s = cooldown_s
        self._clock = clock
        self._exhausted_until: dict[str, float] = {}

    def label_named(self, post: PostText) -> tuple[str, list[Sentiment]]:
        """回傳 (實際使用的 labeler 名稱, 結果)，Label.labeler 要記實際的模型。"""
        now = self._clock()
        for labeler in self._labelers:
            if self._exhausted_until.get(labeler.name, 0.0) > now:
                continue
            try:
                return labeler.name, labeler.label(post)
            except QuotaExhaustedError as e:
                log.warning(
                    "%s exhausted, cooling down %.0fs: %s", labeler.name, self._cooldown_s, e
                )
                self._exhausted_until[labeler.name] = now + self._cooldown_s
        raise AllExhaustedError("all labelers have exhausted their daily quota")

    def close(self) -> None:
        for labeler in self._labelers:
            labeler.close()

import json

import httpx2
import pytest
from pydantic import SecretStr

from radar.common.enums import Polarity
from radar.common.settings import GeminiSettings
from radar.ml.labeling.llm import (
    GeminiLabeler,
    LabelerError,
    LabelerOutputError,
    LabelerSetupError,
    OpenAICompatibleLabeler,
    QuotaExhaustedError,
    RetryableLabelerError,
)
from radar.ml.labeling.prompt import JSON_SCHEMA, RESPONSE_SCHEMA, PostText

SETTINGS = GeminiSettings(api_key=SecretStr("secret-key"))
POST = PostText("Stock.M.1759730000.A.1B2", "Stock", "標題", "內文")
OUTPUT = '{"sentiments": [{"target": null, "polarity": "positive"}]}'


class CountingLimiter:
    def __init__(self) -> None:
        self.calls = 0

    def wait(self) -> float:
        self.calls += 1
        return 0.0


def ok(text: str = OUTPUT, **extra) -> httpx2.Response:
    return httpx2.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": text}]}}], **extra}
    )


def labeler(handler, limiter=None) -> GeminiLabeler:
    return GeminiLabeler(
        "gemini-x",
        SETTINGS,
        limiter or CountingLimiter(),
        max_chars=100,
        transport=httpx2.MockTransport(handler),
    )


def quota_429(quota_id: str) -> httpx2.Response:
    body = {
        "error": {
            "code": 429,
            "details": [
                {
                    "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                    "violations": [{"quotaId": quota_id}],
                }
            ],
        }
    }
    return httpx2.Response(429, json=body)


def test_gemini_label_sends_schema_and_api_key_header():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["key_header"] = request.headers.get("x-goog-api-key")
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return ok()

    labeler(handler).label(POST)

    assert seen["path"] == "/v1beta/models/gemini-x:generateContent"
    assert seen["key_header"] == "secret-key"
    assert "secret-key" not in seen["url"]
    config = seen["body"]["generationConfig"]
    assert config["responseSchema"] == RESPONSE_SCHEMA
    assert config["responseMimeType"] == "application/json"
    assert "標題" in seen["body"]["contents"][0]["parts"][0]["text"]


def test_gemini_label_parses_candidate_text():
    def handler(request):
        parts = [{"text": "thinking...", "thought": True}, {"text": OUTPUT}]
        return httpx2.Response(200, json={"candidates": [{"content": {"parts": parts}}]})

    [sentiment] = labeler(handler).label(POST)

    assert (sentiment.target, sentiment.polarity) == (None, Polarity.POSITIVE)


def test_gemini_label_waits_on_rate_limiter():
    limiter = CountingLimiter()
    lab = labeler(lambda r: ok(), limiter)

    lab.label(POST)
    lab.label(POST)

    assert limiter.calls == 2


def test_gemini_per_minute_429_raises_retryable():
    handler = lambda r: quota_429("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")  # noqa: E731

    with pytest.raises(RetryableLabelerError):
        labeler(handler).label(POST)


def test_gemini_daily_quota_429_raises_quota_exhausted():
    handler = lambda r: quota_429("GenerateRequestsPerDayPerProjectPerModel-FreeTier")  # noqa: E731

    with pytest.raises(QuotaExhaustedError):
        labeler(handler).label(POST)


@pytest.mark.parametrize("status", [500, 503])
def test_gemini_5xx_raises_retryable(status):
    with pytest.raises(RetryableLabelerError):
        labeler(lambda r: httpx2.Response(status)).label(POST)


def test_gemini_connection_error_raises_retryable():
    def handler(request):
        raise httpx2.ConnectError("refused")

    with pytest.raises(RetryableLabelerError):
        labeler(handler).label(POST)


def test_gemini_bad_request_raises_setup_error():
    handler = lambda r: httpx2.Response(400, json={"error": {"message": "bad model"}})  # noqa: E731

    with pytest.raises(LabelerSetupError, match="bad model"):
        labeler(handler).label(POST)


def test_gemini_blocked_prompt_raises_labeler_error():
    handler = lambda r: httpx2.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})  # noqa: E731

    with pytest.raises(LabelerError, match="SAFETY"):
        labeler(handler).label(POST)


def test_gemini_invalid_output_raises_after_one_retry():
    calls = []

    def handler(request):
        calls.append(request)
        return ok("not json")

    with pytest.raises(LabelerOutputError, match="invalid labeler output"):
        labeler(handler).label(POST)
    assert len(calls) == 2


def test_gemini_invalid_output_then_valid_succeeds():
    responses = iter([ok('{"sentiments": []}'), ok()])

    [sentiment] = labeler(lambda r: next(responses)).label(POST)

    assert sentiment.polarity is Polarity.POSITIVE


def test_gemini_empty_candidate_raises_labeler_error():
    def handler(request):
        return httpx2.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS"}]})

    with pytest.raises(LabelerError, match="MAX_TOKENS"):
        labeler(handler).label(POST)


def test_gemini_name_is_model():
    assert labeler(lambda r: ok()).name == "gemini-x"


def compat(handler, limiter=None) -> OpenAICompatibleLabeler:
    return OpenAICompatibleLabeler(
        "groq",
        "qwen/x",
        "https://api.example/openai/v1",
        "bearer-key",
        limiter or CountingLimiter(),
        max_chars=100,
        transport=httpx2.MockTransport(handler),
    )


def chat(content: str | None = OUTPUT, **extra) -> httpx2.Response:
    return httpx2.Response(
        200, json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}], **extra}
    )


def test_compat_sends_json_schema_and_bearer_key():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return chat()

    compat(handler).label(POST)

    assert seen["path"] == "/openai/v1/chat/completions"
    assert seen["auth"] == "Bearer bearer-key"
    assert seen["body"]["model"] == "qwen/x"
    fmt = seen["body"]["response_format"]
    assert (fmt["type"], fmt["json_schema"]["schema"]) == ("json_schema", JSON_SCHEMA)


def test_compat_parses_message_content():
    [sentiment] = compat(lambda r: chat()).label(POST)

    assert (sentiment.target, sentiment.polarity) == (None, Polarity.POSITIVE)


def test_compat_name_includes_provider():
    assert compat(lambda r: chat()).name == "groq:qwen/x"


def test_compat_per_minute_429_raises_retryable():
    body = {"error": {"message": "Rate limit reached on tokens per minute (TPM)"}}

    with pytest.raises(RetryableLabelerError):
        compat(lambda r: httpx2.Response(429, json=body)).label(POST)


@pytest.mark.parametrize(
    "message",
    [
        "Rate limit reached for model on requests per day (RPD): Limit 1000",
        "Rate limit exceeded: free-models-per-day",
    ],
)
def test_compat_daily_429_raises_quota_exhausted(message):
    body = {"error": {"message": message}}

    with pytest.raises(QuotaExhaustedError):
        compat(lambda r: httpx2.Response(429, json=body)).label(POST)


def test_compat_upstream_error_in_200_body_raises_retryable():
    with pytest.raises(RetryableLabelerError, match="upstream"):
        compat(lambda r: chat(error={"code": 502, "message": "provider down"})).label(POST)


def test_compat_unauthorized_raises_setup_error():
    with pytest.raises(LabelerSetupError):
        compat(lambda r: httpx2.Response(401, json={"error": "bad key"})).label(POST)


def test_compat_missing_whole_post_retries_once():
    responses = iter([chat('{"sentiments": [{"target": "7-11", "polarity": "negative"}]}'), chat()])

    [sentiment] = compat(lambda r: next(responses)).label(POST)

    assert sentiment.target is None


def test_compat_empty_content_raises_labeler_error():
    with pytest.raises(LabelerError, match="empty output"):
        compat(lambda r: chat(None)).label(POST)

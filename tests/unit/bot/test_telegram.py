import json

import httpx2
import pytest
from pydantic import SecretStr

from radar.bot.telegram import (
    TelegramBadRequestError,
    TelegramClient,
    TelegramForbiddenError,
    raise_for_response,
)
from radar.common.kafka.consumer import TransientError
from radar.common.settings import TelegramSettings

TOKEN = "123:SECRET"


def response(status: int, body: dict | None = None) -> httpx2.Response:
    return httpx2.Response(status, json=body or {"ok": status == 200})


def client(handler) -> TelegramClient:
    settings = TelegramSettings(bot_token=SecretStr(TOKEN), poll_timeout_s=5)
    return TelegramClient(settings, transport=httpx2.MockTransport(handler))


# --- raise_for_response ---


def test_ok_response_does_not_raise():
    raise_for_response(response(200))


def test_429_raises_transient_with_retry_after():
    with pytest.raises(TransientError) as e:
        raise_for_response(response(429, {"parameters": {"retry_after": 7}}))

    assert e.value.retry_after_s == 7


def test_5xx_raises_transient():
    with pytest.raises(TransientError):
        raise_for_response(response(502))


def test_403_raises_forbidden_with_chat_id():
    with pytest.raises(TelegramForbiddenError) as e:
        raise_for_response(response(403), chat_id=42)

    assert e.value.chat_id == 42


def test_400_raises_bad_request():
    with pytest.raises(TelegramBadRequestError, match="chat not found"):
        raise_for_response(response(400, {"description": "Bad Request: chat not found"}))


def test_non_json_error_body_still_classified():
    with pytest.raises(TransientError):
        raise_for_response(httpx2.Response(503, text="<html>"))


# --- TelegramClient ---


def test_get_updates_passes_offset_and_timeout():
    seen: list[httpx2.Request] = []

    def handler(request):
        seen.append(request)
        return response(200, {"ok": True, "result": []})

    client(handler).get_updates(offset=10, timeout_s=5)

    [req] = seen
    assert req.url.path == f"/bot{TOKEN}/getUpdates"
    assert (req.url.params["offset"], req.url.params["timeout"]) == ("10", "5")


def test_get_updates_non_text_update_has_none_text():
    result = [
        {"update_id": 1, "message": {"chat": {"id": 5}, "text": "/hot"}},
        {"update_id": 2, "message": {"chat": {"id": 5}, "sticker": {}}},
        {"update_id": 3, "edited_message": {}},
    ]

    updates = client(lambda _r: response(200, {"ok": True, "result": result})).get_updates(None, 5)

    assert [(u.update_id, u.chat_id, u.text) for u in updates] == [
        (1, 5, "/hot"),
        (2, 5, None),
        (3, None, None),
    ]


def test_get_updates_connection_error_raises_transient():
    def handler(_request):
        raise httpx2.ConnectError("boom")

    with pytest.raises(TransientError):
        client(handler).get_updates(None, 5)


def test_send_message_posts_chat_id_and_plain_text():
    seen: list[httpx2.Request] = []

    def handler(request):
        seen.append(request)
        return response(200)

    client(handler).send_message(42, "嗨 <b>")

    body = json.loads(seen[0].content)
    assert (body["chat_id"], body["text"]) == (42, "嗨 <b>")
    assert "parse_mode" not in body


def test_send_message_forbidden_carries_chat_id():
    with pytest.raises(TelegramForbiddenError) as e:
        client(lambda _r: response(403)).send_message(42, "x")

    assert e.value.chat_id == 42


def test_token_not_in_error_messages():
    def handler(request):
        raise httpx2.ConnectError(f"cannot reach {request.url}")

    with pytest.raises(TransientError) as e:
        client(handler).send_message(1, "x")

    assert "SECRET" not in str(e.value)
    assert e.value.__cause__ is None

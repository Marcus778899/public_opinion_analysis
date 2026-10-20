import json

import httpx2
import pytest
from pydantic import SecretStr

from radar.bot.telegram import (
    Button,
    TelegramBadRequestError,
    TelegramClient,
    TelegramForbiddenError,
    is_not_modified,
    raise_for_response,
    reply_markup,
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


# --- reply_markup / is_not_modified（S6-01） ---


def test_reply_markup_keeps_rows_and_only_set_fields():
    keyboard = [[Button("訂閱", callback_data="1:sub:Stock")], [Button("原文", url="https://x/")]]

    assert reply_markup(keyboard) == {
        "inline_keyboard": [
            [{"text": "訂閱", "callback_data": "1:sub:Stock"}],
            [{"text": "原文", "url": "https://x/"}],
        ]
    }


def test_is_not_modified_matches_description():
    error = TelegramBadRequestError(
        "telegram 400: Bad Request: message is not modified: specified new message content..."
    )

    assert is_not_modified(error)


def test_is_not_modified_other_bad_request_false():
    assert not is_not_modified(TelegramBadRequestError("telegram 400: chat not found"))


# --- TelegramClient ---


def recorder(seen: list[httpx2.Request], body: dict | None = None):
    def handler(request):
        seen.append(request)
        return response(200, body or {"ok": True, "result": True})

    return handler


def test_get_updates_passes_offset_timeout_and_allowed_updates():
    seen: list[httpx2.Request] = []

    client(recorder(seen, {"ok": True, "result": []})).get_updates(offset=10, timeout_s=5)

    [req] = seen
    assert req.url.path == f"/bot{TOKEN}/getUpdates"
    assert (req.url.params["offset"], req.url.params["timeout"]) == ("10", "5")
    assert json.loads(req.url.params["allowed_updates"]) == ["message", "callback_query"]


def test_get_updates_parses_message_callback_and_other_updates():
    result = [
        {"update_id": 1, "message": {"chat": {"id": 5}, "text": "/hot"}},
        {"update_id": 2, "message": {"chat": {"id": 5}, "sticker": {}}},
        {
            "update_id": 3,
            "callback_query": {
                "id": "cb1",
                "data": "1:nav:hot",
                "message": {"message_id": 77, "chat": {"id": 5}},
            },
        },
        {"update_id": 4, "edited_message": {}},
    ]

    updates = client(lambda _r: response(200, {"ok": True, "result": result})).get_updates(None, 5)

    assert [u.update_id for u in updates] == [1, 2, 3, 4]
    assert (updates[0].message.chat_id, updates[0].message.text) == (5, "/hot")
    assert updates[1].message.text is None
    assert updates[2].callback.model_dump() == {
        "id": "cb1",
        "chat_id": 5,
        "message_id": 77,
        "data": "1:nav:hot",
    }
    assert (updates[3].message, updates[3].callback) == (None, None)


def test_get_updates_connection_error_raises_transient():
    def handler(_request):
        raise httpx2.ConnectError("boom")

    with pytest.raises(TransientError):
        client(handler).get_updates(None, 5)


def test_send_message_uses_html_and_keyboard():
    seen: list[httpx2.Request] = []

    client(recorder(seen)).send_message(42, "嗨 &lt;b&gt;", [[Button("a", callback_data="x")]])

    body = json.loads(seen[0].content)
    assert (body["chat_id"], body["text"], body["parse_mode"]) == (42, "嗨 &lt;b&gt;", "HTML")
    assert body["reply_markup"] == {"inline_keyboard": [[{"text": "a", "callback_data": "x"}]]}
    assert body["disable_web_page_preview"] is True


def test_send_message_without_keyboard_omits_reply_markup():
    seen: list[httpx2.Request] = []

    client(recorder(seen)).send_message(42, "x")

    assert "reply_markup" not in json.loads(seen[0].content)


def test_send_message_forbidden_carries_chat_id():
    with pytest.raises(TelegramForbiddenError) as e:
        client(lambda _r: response(403)).send_message(42, "x")

    assert e.value.chat_id == 42


def test_edit_message_text_posts_ids_and_keyboard():
    seen: list[httpx2.Request] = []

    client(recorder(seen)).edit_message_text(42, 77, "選單", [[Button("a", callback_data="x")]])

    body = json.loads(seen[0].content)
    assert seen[0].url.path.endswith("/editMessageText")
    assert (body["chat_id"], body["message_id"], body["parse_mode"]) == (42, 77, "HTML")


def test_edit_message_text_not_modified_is_success():
    description = "Bad Request: message is not modified"

    client(lambda _r: response(400, {"description": description})).edit_message_text(1, 2, "x")


def test_edit_message_text_other_bad_request_raises():
    with pytest.raises(TelegramBadRequestError):
        client(
            lambda _r: response(400, {"description": "message to edit not found"})
        ).edit_message_text(1, 2, "x")


def test_answer_callback_query_with_and_without_text():
    seen: list[httpx2.Request] = []
    telegram = client(recorder(seen))

    telegram.answer_callback_query("cb1", "已訂閱 Stock")
    telegram.answer_callback_query("cb2")

    bodies = [json.loads(r.content) for r in seen]
    assert bodies == [
        {"callback_query_id": "cb1", "text": "已訂閱 Stock"},
        {"callback_query_id": "cb2"},
    ]


def test_set_my_commands_posts_command_list():
    seen: list[httpx2.Request] = []

    client(recorder(seen)).set_my_commands([("menu", "按鈕選單")])

    assert json.loads(seen[0].content) == {
        "commands": [{"command": "menu", "description": "按鈕選單"}]
    }


def test_token_not_in_error_messages():
    def handler(request):
        raise httpx2.ConnectError(f"cannot reach {request.url}")

    with pytest.raises(TransientError) as e:
        client(handler).send_message(1, "x")

    assert "SECRET" not in str(e.value)
    assert e.value.__cause__ is None

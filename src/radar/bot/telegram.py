"""Telegram Bot API 的最小 client（開發規格 7.21、7.23）：不加 SDK，只包需要的方法。"""

import json
from dataclasses import dataclass
from typing import Any

import httpx2
from pydantic import BaseModel

from radar.common.kafka.consumer import TransientError
from radar.common.settings import TelegramSettings

# long polling 的連線要比 Telegram 端的等待時間長，才不會先被 client 逾時
_TIMEOUT_MARGIN_S = 10.0
_ALLOWED_UPDATES = json.dumps(["message", "callback_query"])


class TelegramForbiddenError(Exception):
    """403：使用者封鎖 bot 或把 bot 移出群組；呼叫端刪掉該 chat 的訂閱。"""

    def __init__(self, chat_id: int | None) -> None:
        super().__init__(f"chat {chat_id} forbidden")
        self.chat_id = chat_id


class TelegramBadRequestError(Exception):
    """400：訊息本身有問題（例如格式錯誤），重送也不會成功；記 WARNING 略過。"""


@dataclass(frozen=True)
class Button:
    """inline keyboard 的一個按鈕；callback_data 與 url 恰好一個。"""

    text: str
    callback_data: str | None = None
    url: str | None = None


# 每個內層 list 是一列按鈕
Keyboard = list[list[Button]]


class IncomingMessage(BaseModel):
    """使用者送出的文字訊息：哪個 chat、送了什麼。"""

    chat_id: int | None
    text: str | None


class CallbackQuery(BaseModel):
    """使用者按了 inline 按鈕；chat_id、message_id 是按鈕所在的那則訊息。"""

    id: str
    chat_id: int | None
    message_id: int | None
    data: str | None


class Update(BaseModel):
    """getUpdates 的一筆；其他類型的 update 兩者皆為 None，offset 仍要前進。"""

    update_id: int
    message: IncomingMessage | None = None
    callback: CallbackQuery | None = None


def reply_markup(keyboard: Keyboard) -> dict[str, list[list[dict[str, str]]]]:
    """Keyboard → Bot API 的 InlineKeyboardMarkup。"""
    return {"inline_keyboard": [[_button(b) for b in row] for row in keyboard]}


def _button(button: Button) -> dict[str, str]:
    if button.url is not None:
        return {"text": button.text, "url": button.url}
    return {"text": button.text, "callback_data": button.callback_data or ""}


class TelegramClient:
    def __init__(self, settings: TelegramSettings, transport: httpx2.BaseTransport | None = None):
        token = settings.bot_token.get_secret_value()
        self._client = httpx2.Client(
            base_url=f"{settings.api_base_url.rstrip('/')}/bot{token}/",
            timeout=settings.poll_timeout_s + _TIMEOUT_MARGIN_S,
            transport=transport,
        )

    def get_updates(self, offset: int | None, timeout_s: int) -> list[Update]:
        """long polling；收 message 與 callback_query，其他類型也回傳，offset 才能前進。"""
        params: dict[str, Any] = {"timeout": timeout_s, "allowed_updates": _ALLOWED_UPDATES}
        if offset is not None:
            params["offset"] = offset
        body = self._call("getUpdates", params=params)
        return [_parse_update(u) for u in body.get("result", [])]

    def send_message(self, chat_id: int, text: str, keyboard: Keyboard | None = None) -> None:
        """text 為 HTML（parse_mode=HTML），外部文字由呼叫端 escape。"""
        payload = _html_payload(chat_id, text, keyboard)
        payload["disable_web_page_preview"] = True
        self._call("sendMessage", json=payload, chat_id=chat_id)

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str, keyboard: Keyboard | None = None
    ) -> None:
        """選單切換時改同一則訊息；內容沒變的 400 視為成功。"""
        payload = _html_payload(chat_id, text, keyboard)
        payload.update(message_id=message_id, disable_web_page_preview=True)
        try:
            self._call("editMessageText", json=payload, chat_id=chat_id)
        except TelegramBadRequestError as e:
            if not is_not_modified(e):
                raise

    def answer_callback_query(self, callback_id: str, text: str | None = None) -> None:
        """每個按鈕回呼都要回應，否則按鈕一直轉圈；text 是畫面上方的短提示。"""
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text is not None:
            payload["text"] = text
        self._call("answerCallbackQuery", json=payload)

    def set_my_commands(self, commands: list[tuple[str, str]]) -> None:
        """註冊指令清單（指令, 說明），輸入 / 時 Telegram 會列出。"""
        items = [{"command": c, "description": d} for c, d in commands]
        self._call("setMyCommands", json={"commands": items})

    def close(self) -> None:
        self._client.close()

    def _call(
        self,
        method: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        chat_id: int | None = None,
    ) -> dict[str, Any]:
        try:
            resp = self._client.post(method, params=params, json=json)
        except httpx2.TransportError as e:
            # NOTE: 例外訊息可能帶完整網址（含 token），只留類別名稱
            raise TransientError(
                f"telegram {method} connection error: {type(e).__name__}"
            ) from None
        raise_for_response(resp, chat_id)
        return resp.json()


def raise_for_response(resp: httpx2.Response, chat_id: int | None = None) -> None:
    """依 Telegram 的回應把錯誤分類（開發規格 7.21）；成功時不做事。"""
    if resp.status_code == 200:
        return
    try:
        body = resp.json()
    except ValueError:
        body = {}
    description = str(body.get("description", ""))[:200]
    if resp.status_code == 429:
        retry_after = (body.get("parameters") or {}).get("retry_after")
        raise TransientError(
            f"telegram rate limited: {description}",
            retry_after_s=float(retry_after) if retry_after is not None else None,
        )
    if resp.status_code >= 500:
        raise TransientError(f"telegram {resp.status_code}: {description}")
    if resp.status_code == 403:
        raise TelegramForbiddenError(chat_id)
    raise TelegramBadRequestError(f"telegram {resp.status_code}: {description}")


def is_not_modified(error: TelegramBadRequestError) -> bool:
    """editMessageText 內容沒變時 Bot API 回 400，視為成功（開發規格 7.23）。"""
    return "message is not modified" in str(error)


def _html_payload(chat_id: int, text: str, keyboard: Keyboard | None) -> dict[str, Any]:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = reply_markup(keyboard)
    return payload


def _parse_update(raw: dict[str, Any]) -> Update:
    message = raw.get("message")
    callback = raw.get("callback_query")
    update = Update(update_id=raw["update_id"])
    if message is not None:
        update.message = IncomingMessage(
            chat_id=(message.get("chat") or {}).get("id"), text=message.get("text")
        )
    if callback is not None:
        origin = callback.get("message") or {}
        update.callback = CallbackQuery(
            id=str(callback["id"]),
            chat_id=(origin.get("chat") or {}).get("id"),
            message_id=origin.get("message_id"),
            data=callback.get("data"),
        )
    return update

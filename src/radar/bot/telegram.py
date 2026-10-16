"""Telegram Bot API 的最小 client（開發規格 7.21）：只用 getUpdates、sendMessage，不加 SDK。"""

from typing import Any

import httpx2
from pydantic import BaseModel

from radar.common.kafka.consumer import TransientError
from radar.common.settings import TelegramSettings

# long polling 的連線要比 Telegram 端的等待時間長，才不會先被 client 逾時
_TIMEOUT_MARGIN_S = 10.0


class TelegramForbiddenError(Exception):
    """403：使用者封鎖 bot 或把 bot 移出群組；呼叫端刪掉該 chat 的訂閱。"""

    def __init__(self, chat_id: int | None) -> None:
        super().__init__(f"chat {chat_id} forbidden")
        self.chat_id = chat_id


class TelegramBadRequestError(Exception):
    """400：訊息本身有問題（例如格式錯誤），重送也不會成功；記 WARNING 略過。"""


class IncomingMessage(BaseModel):
    """getUpdates 中我們需要的部分：哪個 chat、送了什麼文字。"""

    update_id: int
    chat_id: int | None
    text: str | None


class TelegramClient:
    def __init__(self, settings: TelegramSettings, transport: httpx2.BaseTransport | None = None):
        token = settings.bot_token.get_secret_value()
        self._client = httpx2.Client(
            base_url=f"{settings.api_base_url.rstrip('/')}/bot{token}/",
            timeout=settings.poll_timeout_s + _TIMEOUT_MARGIN_S,
            transport=transport,
        )

    def get_updates(self, offset: int | None, timeout_s: int) -> list[IncomingMessage]:
        """long polling；非文字的 update 也要回傳（text 為 None），offset 才能前進。"""
        params: dict[str, Any] = {"timeout": timeout_s, "allowed_updates": '["message"]'}
        if offset is not None:
            params["offset"] = offset
        body = self._call("getUpdates", params=params)
        updates: list[IncomingMessage] = []
        for update in body.get("result", []):
            message = update.get("message") or {}
            updates.append(
                IncomingMessage(
                    update_id=update["update_id"],
                    chat_id=(message.get("chat") or {}).get("id"),
                    text=message.get("text"),
                )
            )
        return updates

    def send_message(self, chat_id: int, text: str) -> None:
        # NOTE: 純文字、不設 parse_mode，標題裡的特殊字元不必跳脫
        self._call(
            "sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            chat_id=chat_id,
        )

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
    """依 Telegram 的回應把錯誤分類（見 send_message）；成功時不做事。"""
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

"""Thin Telegram Bot API client (httpx)."""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .safety import scrub_outbound


class TelegramError(RuntimeError):
    """Raised when the Bot API returns ok=false or HTTP failure."""

    def __init__(self, method: str, description: str, *, error_code: int | None = None):
        self.method = method
        self.description = description
        self.error_code = error_code
        super().__init__(f"Telegram {method} failed: {description}")


class TelegramClient:
    """Minimal async Bot API wrapper used by MCP tools."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0))

    @property
    def base_url(self) -> str:
        return f"{self.settings.api_base.rstrip('/')}/bot{self.settings.bot_token}"

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}/{method}"
        safe_payload = dict(payload or {})
        if method in {"sendMessage", "answerCallbackQuery"}:
            value = safe_payload.get("text")
            if isinstance(value, str):
                safe_payload["text"] = scrub_outbound(value)
        response = await self._client.post(url, json=safe_payload)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(
                method,
                str(data.get("description") or "unknown error"),
                error_code=data.get("error_code"),
            )
        return data.get("result")

    async def get_me(self) -> Any:
        return await self.call("getMe")

    async def get_chat(self, chat_id: int | str) -> Any:
        return await self.call("getChat", {"chat_id": chat_id})

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        parse_mode: str | None = None,
        reply_markup: dict[str, Any] | None = None,
        disable_web_page_preview: bool | None = True,
    ) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": scrub_outbound(text or "")}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if disable_web_page_preview is not None:
            payload["disable_web_page_preview"] = disable_web_page_preview
        return await self.call("sendMessage", payload)

    async def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        *,
        reply_markup: dict[str, Any] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self.call("editMessageReplyMarkup", payload)

    async def answer_callback_query(
        self,
        callback_query_id: str,
        *,
        text: str | None = None,
        show_alert: bool = False,
    ) -> Any:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = scrub_outbound(text)
        if show_alert:
            payload["show_alert"] = True
        return await self.call("answerCallbackQuery", payload)

    async def get_updates(
        self,
        *,
        offset: int | None = None,
        limit: int | None = None,
        timeout: int | None = None,
        allowed_updates: list[str] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {}
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        if timeout is not None:
            payload["timeout"] = timeout
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        return await self.call("getUpdates", payload)

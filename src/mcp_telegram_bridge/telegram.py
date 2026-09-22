"""Thin Telegram Bot API client (httpx)."""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .safety import scrub_outbound

_ERROR_BODY_MAX = 200


def _safe_error_body(response: httpx.Response) -> str:
    """Return a truncated response body safe for logs (never include bot token)."""
    try:
        text = response.text or ""
    except (OSError, UnicodeError, ValueError):
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) > _ERROR_BODY_MAX:
        text = text[:_ERROR_BODY_MAX] + "\u2026"
    return text


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
        """Bot API base URL including the token path segment (not for logging)."""
        return f"{self.settings.api_base.rstrip('/')}/bot{self.settings.bot_token}"

    async def aclose(self) -> None:
        """Close the owned httpx client when this wrapper created it."""
        if self._owns_client:
            await self._client.aclose()

    async def call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        """POST ``method`` to the Bot API and return the ``result`` field.

        On HTTP failure, raises ``TelegramError`` with method, status, and a
        truncated body. The bot token is never included in the error message.
        """
        url = f"{self.base_url}/{method}"
        safe_payload = dict(payload or {})
        if method in {"sendMessage", "answerCallbackQuery"}:
            value = safe_payload.get("text")
            if isinstance(value, str):
                safe_payload["text"] = scrub_outbound(value)
        response = await self._client.post(url, json=safe_payload)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            body = _safe_error_body(exc.response) if exc.response is not None else ""
            raise TelegramError(
                method,
                f"HTTP {status}: {body}" if body else f"HTTP {status}",
                error_code=status,
            ) from None
        data = response.json()
        if not data.get("ok"):
            raise TelegramError(
                method,
                str(data.get("description") or "unknown error"),
                error_code=data.get("error_code"),
            )
        return data.get("result")

    async def get_me(self) -> Any:
        """Return the bot identity from ``getMe"."""
        return await self.call("getMe")

    async def get_chat(self, chat_id: int | str) -> Any:
        """Return chat metadata from ``getChat"."""
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
        """Send scrubbed text via ``sendMessage`` (optional inline keyboard)."""
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
        """Replace or clear inline markup via ``editMessageReplyMarkup"."""
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
        """Acknowledge a callback query (optional scrubbed toast)."""
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
        """Long-poll Telegram updates; the MCP host owns the offset loop."""
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

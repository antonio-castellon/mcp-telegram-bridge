"""Thin Telegram Bot API client (httpx)."""

from __future__ import annotations

from typing import Any

import httpx

from .config import Settings
from .limits import clamp_updates_limit, clamp_updates_timeout
from .redact import install_log_redaction, redact_text
from .safety import scrub_outbound

# Importing this module installs log redaction before the first request.
install_log_redaction(None)

_ERROR_BODY_MAX = 200


def _safe_error_body(response: httpx.Response, token: str | None = None) -> str:
    """Return a truncated response body safe for logs (never include bot token)."""
    try:
        text = response.text or ""
    except (OSError, UnicodeError, ValueError):
        return ""
    text = redact_text(text.replace("\n", " ").strip(), [token] if token else None)
    if len(text) > _ERROR_BODY_MAX:
        text = text[:_ERROR_BODY_MAX] + "..."
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
        install_log_redaction(settings.bot_token)
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0))
        self._own_user_id: int | None = None

    @property
    def base_url(self) -> str:
        """Bot API base URL including the token path segment (not for logging)."""
        return f"{self.settings.api_base.rstrip('/')}/bot{self.settings.bot_token}"

    async def aclose(self) -> None:
        """Close the owned httpx client when this wrapper created it."""
        if self._owns_client:
            await self._client.aclose()

    async def call(
        self,
        method: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: httpx.Timeout | None = None,
    ) -> Any:
        """POST ``method`` to the Bot API and return the ``result`` field.

        On HTTP failure, raises ``TelegramError`` with method, status, and a
        truncated body. The bot token is never included in the error message.
        Transport errors are replaced as well: httpx puts the token-bearing
        URL on the exception.
        """
        url = f"{self.base_url}/{method}"
        safe_payload = dict(payload or {})
        if method in {"sendMessage", "answerCallbackQuery"}:
            value = safe_payload.get("text")
            if isinstance(value, str):
                safe_payload["text"] = scrub_outbound(value)
        # httpx treats timeout=None as "no timeout", not "use the client default".
        request_kwargs: dict[str, Any] = {}
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        try:
            response = await self._client.post(url, json=safe_payload, **request_kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code if exc.response is not None else None
            body = _safe_error_body(exc.response, self.settings.bot_token) if exc.response is not None else ""
            raise TelegramError(
                method,
                f"HTTP {status}: {body}" if body else f"HTTP {status}",
                error_code=status,
            ) from None
        except httpx.HTTPError:
            raise TelegramError(method, "request failed") from None
        try:
            data = response.json()
        except ValueError:
            raise TelegramError(method, "response was not JSON") from None
        if not isinstance(data, dict):
            raise TelegramError(method, "response was not a JSON object")
        if not data.get("ok"):
            description = redact_text(
                str(data.get("description") or "unknown error"),
                [self.settings.bot_token],
            )
            code = data.get("error_code")
            raise TelegramError(
                method,
                description,
                error_code=code if isinstance(code, int) else None,
            )
        return data.get("result")

    async def get_me(self) -> Any:
        """Return the bot identity from ``getMe``."""
        return await self.call("getMe")

    async def own_user_id(self) -> int | None:
        """Best-effort bot user id, cached after the first successful getMe.

        A failure leaves the cache empty so a later poll can try again.
        Callers still ignore ``from.is_bot`` when this returns None.
        """
        if self._own_user_id is not None:
            return self._own_user_id
        try:
            me = await self.get_me()
        except Exception:
            # getMe's failure can carry the token-bearing URL. Swallow the
            # exception object and let callers fall back to from.is_bot.
            return None
        if isinstance(me, dict) and me.get("id") is not None:
            try:
                self._own_user_id = int(me["id"])
            except (TypeError, ValueError):
                return None
        return self._own_user_id

    async def get_chat(self, chat_id: int | str) -> Any:
        """Return chat metadata from ``getChat``."""
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
        """Replace or clear inline markup via ``editMessageReplyMarkup``."""
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
        """Long-poll Telegram updates; the MCP host owns the offset loop.

        ``limit`` is clamped to 1..100 and ``timeout`` to 0..50 so a caller
        cannot ask for an unbounded batch or a poll longer than the client
        timeout.
        """
        limit = clamp_updates_limit(limit)
        timeout = clamp_updates_timeout(timeout)
        payload: dict[str, Any] = {}
        if offset is not None:
            payload["offset"] = offset
        if limit is not None:
            payload["limit"] = limit
        if timeout is not None:
            payload["timeout"] = timeout
        if allowed_updates is not None:
            payload["allowed_updates"] = allowed_updates
        read_timeout = 30.0 + float(timeout or 0)
        return await self.call(
            "getUpdates",
            payload,
            timeout=httpx.Timeout(read_timeout, connect=15.0),
        )

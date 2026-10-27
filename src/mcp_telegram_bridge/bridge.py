"""Telegram bridge library. No MCP imports in this module or its imports."""

from __future__ import annotations

from typing import Any

from . import buttons as btn
from . import safety
from .config import Settings
from .limits import SlidingWindowLimiter, UpdateDeduper, withhold_reason
from .redact import install_log_redaction
from .telegram import TelegramClient


class RateLimitExceeded(RuntimeError):
    """Raised when an outbound call exceeds the configured rate."""


class TelegramBridge:
    """Bot API operations, admission, scrubbing, and inbound bounds.

    Pass a ``Settings`` instance. ``Settings.from_env()`` is the env-based
    default; constructing ``Settings`` directly does not read those variables.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        install_log_redaction(settings.bot_token)
        self.client = TelegramClient(settings)
        self._outbound = SlidingWindowLimiter(
            settings.outbound_chat_rate, settings.outbound_global_rate
        )
        self._inbound_content = SlidingWindowLimiter(
            settings.inbound_chat_rate, settings.inbound_global_rate
        )
        self._inbound_polls = SlidingWindowLimiter(None, settings.inbound_poll_rate)
        self._deduper = UpdateDeduper()

    async def aclose(self) -> None:
        """Close the HTTP client this bridge created."""
        await self.client.aclose()

    async def get_me(self) -> dict[str, Any]:
        """Return the bot identity. Not rate limited."""
        result = await self.client.get_me()
        return {"ok": True, "result": result}

    async def get_chat(self, chat_id: int) -> dict[str, Any]:
        """Return chat metadata for an allowed chat."""
        self._require_chat(chat_id)
        self._require_outbound(chat_id)
        result = await self.client.get_chat(chat_id)
        return {"ok": True, "result": result}

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        buttons: list[dict[str, Any]] | None = None,
        row_width: int = 2,
    ) -> dict[str, Any]:
        """Send scrubbed text. ``buttons`` is a list of ``{id, label}`` dicts."""
        self._require_chat(chat_id)
        self._require_outbound(chat_id)
        scrubbed = safety.scrub_outbound(text or "")
        reply_markup = None
        if buttons:
            reply_markup = self._keyboard(chat_id, buttons, row_width)
        result = await self.client.send_message(
            chat_id,
            scrubbed,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
        )
        return {
            "ok": True,
            "scrubbed": scrubbed != (text or ""),
            "result": result,
        }

    async def edit_reply_markup(
        self,
        chat_id: int,
        message_id: int,
        buttons: list[dict[str, Any]] | None = None,
        row_width: int = 2,
        clear: bool = False,
    ) -> dict[str, Any]:
        """Replace inline buttons, or clear them when ``clear`` is set or buttons is empty."""
        self._require_chat(chat_id)
        self._require_outbound(chat_id)
        if clear or not buttons:
            reply_markup: dict[str, Any] | None = {"inline_keyboard": []}
        else:
            reply_markup = self._keyboard(chat_id, buttons, row_width)
        result = await self.client.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=reply_markup,
        )
        return {"ok": True, "result": result}

    async def answer_callback(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        """Acknowledge a callback. Toast text is scrubbed. Counts against the global outbound rate."""
        self._require_outbound(None)
        toast = safety.scrub_outbound(text) if text else None
        result = await self.client.answer_callback_query(
            callback_query_id,
            text=toast,
            show_alert=show_alert,
        )
        return {"ok": True, "result": result}

    async def get_updates(
        self,
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 0,
    ) -> dict[str, Any]:
        """Poll updates and apply admission, size, rate, dedupe, and bot filtering.

        Delivered text is labeled untrusted. ``limit`` and ``timeout`` are clamped
        by the HTTP client (1..100 and 0..50).
        """
        if not self._inbound_polls.allow(None):
            wait = round(self._inbound_polls.retry_after(None), 1)
            return _updates_result(
                ok=False,
                rate_limited=True,
                error="inbound poll rate limit exceeded",
                retry_after_seconds=wait,
            )
        raw = await self.client.get_updates(
            offset=offset,
            limit=limit,
            timeout=timeout,
            allowed_updates=["message", "edited_message", "callback_query"],
        )
        own_id = await self.client.own_user_id()
        updates: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        callback_queries: list[dict[str, Any]] = []
        summary = {
            "delivered": 0,
            "filtered": 0,
            "ignored": 0,
            "duplicates": 0,
            "rate_limited": 0,
        }
        highest: int | None = None
        retry_after = 0.0
        cfg = self.settings
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            update_id = _coerce_update_id(item.get("update_id"))
            if update_id is not None:
                highest = update_id if highest is None else max(highest, update_id)
            if update_id is not None and self._deduper.contains(update_id):
                updates.append(
                    {
                        "update_id": update_id,
                        "duplicate": True,
                        "ignored": True,
                        "ignore_reason": "duplicate",
                    }
                )
                summary["duplicates"] += 1
                continue
            chat_id = _extract_chat_id(item)
            blocked = _chat_block_reason(cfg, chat_id)
            if blocked is not None:
                updates.append(_filtered_stub(item, blocked, strict=cfg.safety_strict))
                summary["filtered"] += 1
                continue
            ignore = _ignore_reason(item, own_id)
            if ignore is not None:
                updates.append(
                    {
                        "update_id": item.get("update_id"),
                        "ignored": True,
                        "ignore_reason": ignore,
                    }
                )
                summary["ignored"] += 1
                continue
            too_big = withhold_reason(
                item,
                max_chars=cfg.max_inbound_chars,
                max_bytes=cfg.max_update_bytes,
            )
            if too_big is not None:
                updates.append(_filtered_stub(item, too_big, strict=cfg.safety_strict))
                summary["filtered"] += 1
                continue
            rate_key = "unknown" if chat_id is None else str(chat_id)
            if not self._inbound_content.allow(rate_key):
                updates.append(
                    _filtered_stub(
                        item,
                        "rate limit",
                        strict=cfg.safety_strict,
                        rate_limited=True,
                    )
                )
                summary["rate_limited"] += 1
                retry_after = max(retry_after, self._inbound_content.retry_after(rate_key))
                continue
            annotated = safety.annotate_update(item) if cfg.safety_strict else dict(item)
            cq = annotated.get("callback_query")
            if isinstance(cq, dict) and cq.get("data") and chat_id is not None:
                resolved = btn.resolve_callback_data(
                    cfg.data_dir, int(chat_id), str(cq["data"])
                )
                cq = dict(cq)
                cq["data"] = resolved
                raw_cq = item.get("callback_query")
                cq["data_raw"] = raw_cq.get("data") if isinstance(raw_cq, dict) else None
                annotated["callback_query"] = cq
            annotated = safety.mark_untrusted(annotated)
            if update_id is not None:
                self._deduper.remember(update_id)
            updates.append(annotated)
            summary["delivered"] += 1
            if "message" in annotated or "edited_message" in annotated:
                messages.append(annotated)
            if "callback_query" in annotated:
                callback_queries.append(annotated)
        extra: dict[str, Any] = {}
        if retry_after > 0:
            extra["retry_after_seconds"] = round(retry_after, 1)
        return _updates_result(
            updates=updates,
            messages=messages,
            callback_queries=callback_queries,
            next_offset=None if highest is None else highest + 1,
            summary=summary,
            **extra,
        )

    def _require_chat(self, chat_id: int) -> None:
        reason = _chat_block_reason(self.settings, chat_id)
        if reason is not None:
            raise PermissionError(reason)

    def _require_outbound(self, chat_id: int | None) -> None:
        key = None if chat_id is None else str(chat_id)
        if self._outbound.allow(key):
            return
        wait = round(self._outbound.retry_after(key), 1)
        target = "this call" if chat_id is None else f"chat_id {chat_id}"
        raise RateLimitExceeded(
            f"outbound rate limit exceeded for {target}; retry after {wait}s"
        )

    def _keyboard(
        self,
        chat_id: int,
        buttons: list[dict[str, Any]],
        row_width: int,
    ) -> dict[str, Any]:
        raw_buttons = []
        for button in buttons:
            if not isinstance(button, dict):
                raise TypeError("buttons must be a list of dicts")
            raw_buttons.append(
                {
                    **button,
                    "id": safety.scrub_outbound(str(button.get("id") or "")),
                    "label": safety.scrub_outbound(
                        str(button.get("label") or button.get("text") or "")
                    ),
                }
            )
        normalized = btn.normalize_buttons(raw_buttons)
        return btn.build_inline_keyboard(
            normalized,
            chat_id=chat_id,
            data_dir=self.settings.data_dir,
            row_width=row_width,
        )


def _updates_result(
    *,
    updates: list[dict[str, Any]] | None = None,
    messages: list[dict[str, Any]] | None = None,
    callback_queries: list[dict[str, Any]] | None = None,
    next_offset: int | None = None,
    summary: dict[str, int] | None = None,
    ok: bool = True,
    **extra: Any,
) -> dict[str, Any]:
    body = updates or []
    result = {
        "ok": ok,
        "untrusted": True,
        "trust_boundary": safety.TRUST_BOUNDARY,
        "updates": body,
        "messages": messages or [],
        "callback_queries": callback_queries or [],
        "count": len(body),
        "next_offset": next_offset,
        "summary": summary
        or {
            "delivered": 0,
            "filtered": 0,
            "ignored": 0,
            "duplicates": 0,
            "rate_limited": 0,
        },
    }
    result.update(extra)
    return result


def _filtered_stub(
    item: dict[str, Any],
    reason: str,
    *,
    strict: bool,
    rate_limited: bool = False,
) -> dict[str, Any]:
    stub: dict[str, Any] = {
        "update_id": item.get("update_id"),
        "filtered": True,
        "filter_reason": reason,
    }
    if rate_limited:
        stub["rate_limited"] = True
    if strict:
        stub["safety"] = {"kind": "policy", "blocked": True, "warning": reason}
    return stub


def _coerce_update_id(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _sender(update: dict[str, Any]) -> dict[str, Any] | None:
    msg = update.get("message") or update.get("edited_message")
    if isinstance(msg, dict) and isinstance(msg.get("from"), dict):
        return msg["from"]
    callback = update.get("callback_query")
    if isinstance(callback, dict) and isinstance(callback.get("from"), dict):
        return callback["from"]
    return None


def _on_behalf_of_chat(update: dict[str, Any]) -> bool:
    """True when Telegram attributes the message to a chat, not a bot user.

    Anonymous admin posts and messages sent as a channel use ``sender_chat``
    and a bot-shaped ``from``. Those are not bot-to-bot loops.
    """
    for key in ("message", "edited_message"):
        msg = update.get(key)
        if isinstance(msg, dict) and isinstance(msg.get("sender_chat"), dict):
            return True
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        msg = callback.get("message")
        if isinstance(msg, dict) and isinstance(msg.get("sender_chat"), dict):
            return True
    return False


def _ignore_reason(update: dict[str, Any], own_user_id: int | None) -> str | None:
    sender = _sender(update)
    if sender is None:
        return None
    sender_id = sender.get("id")
    if own_user_id is not None and sender_id is not None:
        try:
            if int(sender_id) == int(own_user_id):
                return "self"
        except (TypeError, ValueError):
            pass
    if sender.get("is_bot") is True and not _on_behalf_of_chat(update):
        return "bot"
    return None


def _chat_block_reason(cfg: Settings, chat_id: int | None) -> str | None:
    if cfg.open_mode:
        return None
    if chat_id is None:
        if cfg.allowed_chat_ids:
            return "chat_id unavailable; ALLOWED_CHAT_IDS is configured"
        return "chat_id unavailable; ALLOWED_CHAT_IDS is empty and open mode is off"
    if cfg.chat_allowed(chat_id):
        return None
    if cfg.allowed_chat_ids:
        return f"chat_id {chat_id} is not in ALLOWED_CHAT_IDS"
    return (
        f"chat_id {chat_id} is not allowed. ALLOWED_CHAT_IDS is empty; "
        "set an allowlist or opt in with ALLOW_ALL_CHATS=1"
    )


def _extract_chat_id(update: dict[str, Any]) -> int | None:
    msg = update.get("message") or update.get("edited_message")
    if isinstance(msg, dict):
        chat = msg.get("chat") or {}
        if isinstance(chat, dict) and chat.get("id") is not None:
            return int(chat["id"])
    cq = update.get("callback_query")
    if isinstance(cq, dict):
        msg = cq.get("message") or {}
        if isinstance(msg, dict):
            chat = msg.get("chat") or {}
            if isinstance(chat, dict) and chat.get("id") is not None:
                return int(chat["id"])
    return None

"""MCP server: Telegram I/O tools + safety. Agent owns conversation logic."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from . import buttons as btn
from . import safety
from .config import Settings, load_dotenv_if_present
from .telegram import TelegramClient

INSTRUCTIONS = """\
Controlled Telegram channel bridge (stdio MCP).

This server only does Bot API I/O plus inbound classify / outbound scrub.
The MCP host agent owns conversation logic, polling loops, and product rules.
Games / GM flows are one demo use case — not the product.

Tools: telegram_get_me, telegram_send_message, telegram_edit_reply_markup,
telegram_answer_callback, telegram_get_updates, telegram_get_chat.
"""


class ButtonSpec(BaseModel):
    id: str = Field(..., description="Opaque button id returned in callback_query.data")
    label: str = Field(..., description="Visible button label (max ~64 chars)")


def create_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP app with Telegram tools registered."""
    load_dotenv_if_present()
    cfg = settings or Settings.from_env(require_token=True)
    client = TelegramClient(cfg)

    mcp = FastMCP(
        name="mcp-telegram-bridge",
        instructions=INSTRUCTIONS,
    )

    def _require_chat(chat_id: int) -> None:
        if not cfg.chat_allowed(chat_id):
            raise PermissionError(
                f"chat_id {chat_id} is not in ALLOWED_CHAT_IDS"
            )

    @mcp.tool(
        name="telegram_get_me",
        description="Return the bot identity (getMe). Useful as a connectivity check.",
    )
    async def telegram_get_me() -> dict[str, Any]:
        result = await client.get_me()
        return {"ok": True, "result": result}

    @mcp.tool(
        name="telegram_get_chat",
        description="Fetch chat metadata (getChat) for a chat_id.",
    )
    async def telegram_get_chat(chat_id: int) -> dict[str, Any]:
        _require_chat(chat_id)
        result = await client.get_chat(chat_id)
        return {"ok": True, "result": result}

    @mcp.tool(
        name="telegram_send_message",
        description=(
            "Send a text message. Outbound text is scrubbed for token-shaped secrets. "
            "Optional buttons=[{id,label}] become an inline keyboard."
        ),
    )
    async def telegram_send_message(
        chat_id: int,
        text: str,
        parse_mode: str | None = None,
        buttons: list[ButtonSpec] | None = None,
        row_width: int = 2,
    ) -> dict[str, Any]:
        _require_chat(chat_id)
        scrubbed = safety.scrub_outbound(text or "")
        reply_markup = None
        if buttons:
            raw_buttons = [
                b.model_dump() if isinstance(b, BaseModel) else dict(b) for b in buttons
            ]
            normalized = btn.normalize_buttons(raw_buttons)
            reply_markup = btn.build_inline_keyboard(
                normalized,
                chat_id=chat_id,
                data_dir=cfg.data_dir,
                row_width=row_width,
            )
        result = await client.send_message(
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

    @mcp.tool(
        name="telegram_edit_reply_markup",
        description=(
            "Edit or clear inline buttons on an existing message. "
            "Pass buttons=null/omit to strip markup; or a new [{id,label}] list."
        ),
    )
    async def telegram_edit_reply_markup(
        chat_id: int,
        message_id: int,
        buttons: list[ButtonSpec] | None = None,
        row_width: int = 2,
        clear: bool = False,
    ) -> dict[str, Any]:
        _require_chat(chat_id)
        if clear or not buttons:
            reply_markup: dict[str, Any] | None = {"inline_keyboard": []}
        else:
            raw_buttons = [
                b.model_dump() if isinstance(b, BaseModel) else dict(b) for b in buttons
            ]
            normalized = btn.normalize_buttons(raw_buttons)
            reply_markup = btn.build_inline_keyboard(
                normalized,
                chat_id=chat_id,
                data_dir=cfg.data_dir,
                row_width=row_width,
            )
        result = await client.edit_message_reply_markup(
            chat_id,
            message_id,
            reply_markup=reply_markup,
        )
        return {"ok": True, "result": result}

    @mcp.tool(
        name="telegram_answer_callback",
        description="Acknowledge a callback_query (optional toast text / alert).",
    )
    async def telegram_answer_callback(
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:
        toast = safety.scrub_outbound(text) if text else None
        result = await client.answer_callback_query(
            callback_query_id,
            text=toast,
            show_alert=show_alert,
        )
        return {"ok": True, "result": result}

    @mcp.tool(
        name="telegram_get_updates",
        description=(
            "Long-poll getUpdates. The agent owns the offset loop. "
            "Each update is annotated with safety.{kind,blocked,warning}; "
            "dangerous inbound is flagged, not silently dropped."
        ),
    )
    async def telegram_get_updates(
        offset: int | None = None,
        limit: int = 100,
        timeout: int = 0,
    ) -> dict[str, Any]:
        raw = await client.get_updates(
            offset=offset,
            limit=limit,
            timeout=timeout,
            allowed_updates=["message", "edited_message", "callback_query"],
        )
        updates: list[dict[str, Any]] = []
        messages: list[dict[str, Any]] = []
        callback_queries: list[dict[str, Any]] = []
        for item in raw or []:
            if not isinstance(item, dict):
                continue
            # Optional allow-list filter on chat ids
            chat_id = _extract_chat_id(item)
            if chat_id is not None and not cfg.chat_allowed(chat_id):
                annotated = {
                    "update_id": item.get("update_id"),
                    "safety": {
                        "kind": "secrets",
                        "blocked": True,
                        "warning": f"chat_id {chat_id} not in ALLOWED_CHAT_IDS",
                    },
                    "filtered": True,
                }
                updates.append(annotated)
                continue
            annotated = safety.annotate_update(item)
            # Resolve mapped callback ids for the agent
            cq = annotated.get("callback_query")
            if isinstance(cq, dict) and cq.get("data") and chat_id is not None:
                resolved = btn.resolve_callback_data(
                    cfg.data_dir, int(chat_id), str(cq["data"])
                )
                cq = dict(cq)
                cq["data"] = resolved
                cq["data_raw"] = item.get("callback_query", {}).get("data")
                annotated["callback_query"] = cq
            updates.append(annotated)
            if "message" in annotated or "edited_message" in annotated:
                messages.append(annotated)
            if "callback_query" in annotated:
                callback_queries.append(annotated)
        return {
            "ok": True,
            "updates": updates,
            "messages": messages,
            "callback_queries": callback_queries,
            "count": len(updates),
        }

    # Expose for tests / cleanup
    mcp._telegram_client = client  # type: ignore[attr-defined]
    mcp._settings = cfg  # type: ignore[attr-defined]
    return mcp


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


def list_tool_names(server: FastMCP | None = None) -> list[str]:
    """Return registered tool names (for smoke tests without stdio)."""
    app = server or create_server(
        Settings(bot_token="000000000:TEST_TOKEN_PLACEHOLDER_XXXXXXXX", allowed_chat_ids=frozenset())
    )
    tools = app._tool_manager.list_tools()
    return sorted(t.name for t in tools)


def main() -> None:
    """Entrypoint: run stdio MCP server."""
    load_dotenv_if_present()
    settings = Settings.from_env(require_token=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app = create_server(settings)
    app.run(transport="stdio")

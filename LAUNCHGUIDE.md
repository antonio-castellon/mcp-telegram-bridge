# mcp-telegram-bridge

## Tagline
Stdio MCP bridge to Telegram Bot API with scrubbing and chat allowlist.

## Description
Controlled Telegram channel bridge for any MCP host (Cursor, Claude Desktop, Windsurf, and others). A small stdio Model Context Protocol server that sits between your local agent and the Telegram Bot API. The agent owns conversation logic; this process handles I/O, always-on outbound secret scrubbing, and optional chat allowlist enforcement. Optional strict inbound classification is off by default.

Built for client-owned deployments: the bridge runs on your machine. Games and game-master flows are one demo use case, not the product. Same control-layer pattern is useful for SME notify channels, specialist handoff, and moderated drafts alongside email or ERP connectors.

## Setup Requirements
- `TELEGRAM_BOT_TOKEN` (required): Bot token from @BotFather. Never commit this value.
- `ALLOWED_CHAT_IDS` (recommended): Comma-separated Telegram chat IDs the bridge may send to. Leave empty only if you intentionally accept every chat the bot can see.
- `SAFETY_STRICT` (optional): Set to `1` / `true` / `yes` / `on` to enable heuristic inbound secret/NSFW classification on `telegram_get_updates`. Default is off.
- `MCP_TELEGRAM_BRIDGE_DATA_DIR` (optional): Directory for button-map / claim state (defaults to platform user data dir). Created with restrictive permissions when possible.

Install: `uvx --from mcp-telegram-bridge mcp-telegram-bridge` (or `pip install mcp-telegram-bridge`). Requires Python 3.11+.

## Category
Communication

## Use Cases
Agent notify channels, Collaborative Telegram groups, Support/ops ack buttons, Game master demo buttons, SME lab triage handoff

## Features
- Stdio MCP server for any local MCP host
- Telegram Bot API send / edit markup / answer callback / getUpdates / getMe / getChat
- Always-on outbound secret scrubbing
- Optional chat allowlist (`ALLOWED_CHAT_IDS`)
- Optional strict inbound classification (`SAFETY_STRICT`)
- Inline buttons with atomic first-tap claim helpers
- Client-owned: no hosted multi-tenant bot SaaS
- Hardened local data directory for button maps

## Getting Started
- "Check that the Telegram bot is online" → uses `telegram_get_me`
- "Send this triage note to the ops chat with Ack / Snooze buttons" → `telegram_send_message` with buttons
- "Poll for new messages and button taps" → `telegram_get_updates` (agent owns the offset loop)
- "Clear the spent buttons on that message" → `telegram_edit_reply_markup`
- "Acknowledge this callback query" → `telegram_answer_callback`

## Tags
telegram, mcp, stdio, bot-api, bridge, scrubbing, allowlist, safety, cursor, local

## Documentation URL
https://github.com/antonio-castellon/mcp-telegram-bridge

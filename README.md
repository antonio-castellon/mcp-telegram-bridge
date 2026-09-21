# mcp-telegram-bridge

**Controlled Telegram channel bridge for any MCP host.**

A small stdio [Model Context Protocol](https://modelcontextprotocol.io/) server that sits between your local agent (Cursor, Claude Desktop, Windsurf, Grok/Cursor agents, and others) and the Telegram Bot API. The agent owns conversation logic; this process handles I/O, always-on outbound scrubbing, and chat allowlist enforcement. Optional strict inbound classification is disabled by default.

Built for client-owned deployments â€” the bridge runs on **your machine**, not on a hosted Grok VM. Games and game-master flows are one demo use case, not the product.

Owner context: [Antonio Castellon](https://castellon.ch) / Castellon.CH â€” Swiss freelance architect. The same bridge shape is useful for SME lab patterns (notify channels, specialist handoff, moderated drafts) alongside email or ERP connectors.

## What / why

Agents are good at reasoning and poor at holding a raw Bot API session by themselves. Telegram is a convenient human surface (groups, buttons, mobile). This project gives you a **narrow, reviewable bridge**:

- **Client-owned** â€” stdio MCP on the workstation or CI runner that already hosts your agent.
- **Host-agnostic** â€” any MCP client that can launch a local command.
- **Controlled** â€” outbound scrubbing and optional `ALLOWED_CHAT_IDS`; optional strict inbound classification for untrusted groups.
- **Minimal tools** â€” send, edit markup, answer callbacks, get updates, getMe / getChat. No game engine, no inbox file, no wake-RPC.

Pitch pattern for SMEs: start with a Telegram notify or triage channel using the same architecture you would later apply to email or ERP.

## Architecture

```
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚  MCP host / agents      â”‚  Cursor Â· Claude Desktop Â· Windsurf Â· â€¦
  â”‚  (conversation logic)   â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
              â”‚  MCP (stdio)
              â–¼
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚  mcp-telegram-bridge    â”‚  tools + safety scrub/classify
  â”‚  (this process)         â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
              â”‚  HTTPS Bot API
              â–¼
  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
  â”‚  api.telegram.org       â”‚
  â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
              â–¼
         Telegram chats / groups
```

The **agent** owns polling offsets, handoffs between specialists, and product policy. This server enforces destination controls and sends scrubbed text; inbound classification is opt-in.

## Install

Requirements: Python 3.11+, a Telegram bot token from [@BotFather](https://t.me/BotFather).

```bash
git clone https://github.com/antonio-castellon/mcp-telegram-bridge.git
cd mcp-telegram-bridge
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env        # set TELEGRAM_BOT_TOKEN (never commit .env)
```

Or without cloning, once published:

```bash
uvx --from mcp-telegram-bridge mcp-telegram-bridge
# or: pipx run mcp-telegram-bridge
```

### Cursor / Claude Desktop (`mcp.json`)

Example for Cursor (User MCP settings) or Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "telegram-bridge": {
      "command": "uvx",`r`n      "args": ["--from", "mcp-telegram-bridge", "mcp-telegram-bridge"],
      "env": {
        "TELEGRAM_BOT_TOKEN": "YOUR_BOT_TOKEN_HERE",
        "ALLOWED_CHAT_IDS": "-1001234567890"
      }
    }
  }
}
```

On Windows, point `command` at your venv Python if needed, for example:

`C:\\DEV.Personal\\mcp-telegram-bridge\\.venv\\Scripts\\python.exe`

Leave `ALLOWED_CHAT_IDS` empty only if you intentionally accept traffic from every chat the bot can see â€” document that risk for your deployment.

Smoke without a host:

```bash
python -m mcp_telegram_bridge
# process waits on stdio for MCP JSON-RPC (Ctrl+C to stop)
```

## MCP tools

| Tool | Purpose |
|---|---|
| `telegram_get_me` | Bot identity / connectivity check |
| `telegram_send_message` | `chat_id`, `text`, optional `parse_mode`, optional `buttons=[{id,label}]` |
| `telegram_edit_reply_markup` | Strip or replace inline buttons |
| `telegram_answer_callback` | Ack a `callback_query_id` (optional toast) |
| `telegram_get_updates` | `offset`, `limit`, `timeout` â€” returns messages + callback_queries; **agent owns the loop** |
| `telegram_get_chat` | Chat metadata |

Outbound text is always scrubbed. `ALLOWED_CHAT_IDS` restricts destinations when configured. `telegram_get_updates` runs the heuristic secret/NSFW classifier only when `SAFETY_STRICT=1` (or `true`/`yes`/`on`); strict mode is optional and recommended for public or untrusted groups.

## Usage guide

### Collaborative agents in a Telegram group

Run one bridge process per bot (or one bot with clear agent roles). Use the group for standup notes, triage queues, and handoff between specialist agents (â€œops acknowledges; billing drafts the replyâ€). Keep humans in the loop for irreversible actions.

### Game master / tabletop facilitator (demo)

Send scene text with `buttons=[{id,label}, â€¦]` for player choices; on `callback_query`, answer the callback, optionally `claim`-style first-tap handling in the agent, then edit markup to clear spent choices. This is a **demo** of buttons + agent loop â€” not a bundled RPG engine.

### Support / ops notify channel

Push alerts with ack buttons (`ack`, `snooze`, `escalate`). The agent records who tapped what; Telegram is the pager surface, not the source of truth.

### Community moderation assistant

Draft replies and suggest actions. **Humans still own ban / restrict / delete** in Telegram Admin â€” say so in your agent prompt. The bridge must not be treated as a moderation authority.

### Lab / SME pattern

Same shape as an email or ERP connector: narrow tools, allow-listed destinations, scrubbed egress, explicit inbound warnings. Telegram is the demo channel; swap the transport later without rewriting agent policy.

## What this is NOT

- Not a hosted bot SaaS or multi-tenant cloud bridge
- Not Grok-only (works with any stdio MCP host)
- Not a full RPG / game engine (no dice ruleset, no campaign DB in this repo)
- Not an unattended admin bot (no ban tools shipped here)

## Relation to sibling demos

Optional context only â€” this project does **not** require them:

- [grokgame](https://github.com/antonio-castellon/grokgame) â€” tabletop / game demo surface
- [grok2telegram](https://github.com/antonio-castellon/grok2telegram) â€” earlier bridge experiment whose safety doctrine informed `SAFETY.md` and `safety.py`

`mcp-telegram-bridge` is the reusable, host-agnostic extraction: I/O + safety, no game loop and no Grok VM wake logic.

## Safety

See **[SAFETY.md](SAFETY.md)** for the threat model, always-on scrubbing and allowlist controls, token handling, and optional strict mode. Do not put secrets in the repository; prefer `ALLOWED_CHAT_IDS` in production-like setups.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests mock Telegram HTTP with `respx` / `httpx`; no live token required.

## MCP Registry

Canonical name: `io.github.antonio-castellon/mcp-telegram-bridge`

<!-- mcp-name: io.github.antonio-castellon/mcp-telegram-bridge -->

## License

MIT Â© Antonio Castellon / Castellon.CH


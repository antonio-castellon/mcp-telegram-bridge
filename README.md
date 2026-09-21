# mcp-telegram-bridge

**Controlled Telegram channel bridge for any MCP host.**

A small stdio [Model Context Protocol](https://modelcontextprotocol.io/) server that sits between your local agent (Cursor, Claude Desktop, Windsurf, Grok/Cursor agents, and others) and the Telegram Bot API. The agent owns conversation logic; this process handles I/O, always-on outbound scrubbing, and chat allowlist enforcement. Optional strict inbound classification is disabled by default.

Built for client-owned deployments — the bridge runs on **your machine**, not on a hosted Grok VM. Games and game-master flows are one demo use case, not the product.

Owner context: [Antonio Castellon](https://castellon.ch) / Castellon.CH — Swiss freelance architect. The same bridge shape is useful for SME lab patterns (notify channels, specialist handoff, moderated drafts) alongside email or ERP connectors.

## What / why

Agents are good at reasoning and poor at holding a raw Bot API session by themselves. Telegram is a convenient human surface (groups, buttons, mobile). This project gives you a **narrow, reviewable bridge**:

- **Client-owned** — stdio MCP on the workstation or CI runner that already hosts your agent.
- **Host-agnostic** — any MCP client that can launch a local command.
- **Controlled** — outbound scrubbing and optional `ALLOWED_CHAT_IDS`; optional strict inbound classification for untrusted groups.
- **Minimal tools** — send, edit markup, answer callbacks, get updates, getMe / getChat. No game engine, no inbox file, no wake-RPC.

Pitch pattern for SMEs: start with a Telegram notify or triage channel using the same architecture you would later apply to email or ERP.

## Architecture

```
  ┌─────────────────────────┐
  │  MCP host / agents      │  Cursor · Claude Desktop · Windsurf · …
  │  (conversation logic)   │
  └───────────┬─────────────┘
              │  MCP (stdio)
              ▼
  ┌─────────────────────────┐
  │  mcp-telegram-bridge    │  tools + safety scrub/classify
  │  (this process)         │
  └───────────┬─────────────┘
              │  HTTPS Bot API
              ▼
  ┌─────────────────────────┐
  │  api.telegram.org       │
  └───────────┬─────────────┘
              ▼
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
      "command": "python",
      "args": ["-m", "mcp_telegram_bridge"],
      "cwd": "/absolute/path/to/mcp-telegram-bridge",
      "env": {
        "TELEGRAM_BOT_TOKEN": "123456:REPLACE_ME",
        "ALLOWED_CHAT_IDS": "-1001234567890"
      }
    }
  }
}
```

On Windows, point `command` at your venv Python if needed, for example:

`C:\\DEV.Personal\\mcp-telegram-bridge\\.venv\\Scripts\\python.exe`

Leave `ALLOWED_CHAT_IDS` empty only if you intentionally accept traffic from every chat the bot can see — document that risk for your deployment.

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
| `telegram_get_updates` | `offset`, `limit`, `timeout` — returns messages + callback_queries; **agent owns the loop** |
| `telegram_get_chat` | Chat metadata |

Outbound text is always scrubbed. `ALLOWED_CHAT_IDS` restricts destinations when configured. `telegram_get_updates` runs the heuristic secret/NSFW classifier only when `SAFETY_STRICT=1` (or `true`/`yes`/`on`); strict mode is optional and recommended for public or untrusted groups.

## Usage guide

### Collaborative agents in a Telegram group

Run one bridge process per bot (or one bot with clear agent roles). Use the group for standup notes, triage queues, and handoff between specialist agents (“ops acknowledges; billing drafts the reply”). Keep humans in the loop for irreversible actions.

### Game master / tabletop facilitator (demo)

Send scene text with `buttons=[{id,label}, …]` for player choices; on `callback_query`, answer the callback, optionally `claim`-style first-tap handling in the agent, then edit markup to clear spent choices. This is a **demo** of buttons + agent loop — not a bundled RPG engine.

### Support / ops notify channel

Push alerts with ack buttons (`ack`, `snooze`, `escalate`). The agent records who tapped what; Telegram is the pager surface, not the source of truth.

### Community moderation assistant

Draft replies and suggest actions. **Humans still own ban / restrict / delete** in Telegram Admin — say so in your agent prompt. The bridge must not be treated as a moderation authority.

### Lab / SME pattern

Same shape as an email or ERP connector: narrow tools, allow-listed destinations, scrubbed egress, explicit inbound warnings. Telegram is the demo channel; swap the transport later without rewriting agent policy.

## What this is NOT

- Not a hosted bot SaaS or multi-tenant cloud bridge
- Not Grok-only (works with any stdio MCP host)
- Not a full RPG / game engine (no dice ruleset, no campaign DB in this repo)
- Not an unattended admin bot (no ban tools shipped here)

## Relation to sibling demos

Optional context only — this project does **not** require them:

- [grokgame](https://github.com/antonio-castellon/grokgame) — tabletop / game demo surface
- [grok2telegram](https://github.com/antonio-castellon/grok2telegram) — earlier bridge experiment whose safety doctrine informed `SAFETY.md` and `safety.py`

`mcp-telegram-bridge` is the reusable, host-agnostic extraction: I/O + safety, no game loop and no Grok VM wake logic.

## Safety

See **[SAFETY.md](SAFETY.md)** for the threat model, always-on scrubbing and allowlist controls, token handling, and optional strict mode. Do not put secrets in the repository; prefer `ALLOWED_CHAT_IDS` in production-like setups.

## Development

```bash
pip install -e ".[dev]"
pytest
```

Tests mock Telegram HTTP with `respx` / `httpx`; no live token required.

## Publishing note

Ready for review. Directory layout and packaging are set for a later public GitHub release (`antonio-castellon/mcp-telegram-bridge`). Do not commit `.env` or real chat ids.

## License

MIT © Antonio Castellon / Castellon.CH

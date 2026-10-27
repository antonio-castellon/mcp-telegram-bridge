<p>
  <a href="https://github.com/antonio-castellon/mcp-telegram-bridge/releases/latest"><img src="https://img.shields.io/github/v/release/antonio-castellon/mcp-telegram-bridge" alt="Latest GitHub release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license"></a>
  <img src="https://img.shields.io/pypi/pyversions/mcp-telegram-bridge" alt="Python versions">
  <a href="https://modelcontextprotocol.io/"><img src="https://img.shields.io/badge/MCP-stdio-111827" alt="MCP stdio"></a>
</p>

![mcp-telegram-bridge](https://raw.githubusercontent.com/antonio-castellon/mcp-telegram-bridge/main/docs/images/banner.png)

# mcp-telegram-bridge

[![Listed on mcpservers.org](https://mcpservers.org/badge.svg)](https://mcpservers.org/servers/antonio-castellon/mcp-telegram-bridge)

**Stdio MCP bridge to the Telegram Bot API, with fail-closed chat admission and outbound scrubbing.**

A small [Model Context Protocol](https://modelcontextprotocol.io/) server that a local agent (Cursor, Claude Desktop, Windsurf, and others) launches on your machine. The agent owns the conversation. This process does Bot API I/O, scrubs outbound secrets, and refuses chats you have not allowed.

Version 0.2.0 changes admission: an empty allowlist denies every chat. Set `ALLOWED_CHAT_IDS`, or opt in to open mode with `ALLOW_ALL_CHATS=1`.

Built for client-owned deployments. The bridge is not a hosted bot service. Games and game-master flows are one demo use case, not the product.

Owner: [Antonio Castellon](https://castellon.ch) / Castellon.CH.

## Quick start

Requirements: Python 3.11+, a bot token from [@BotFather](https://t.me/BotFather), and the numeric id of the chat you want the bot to use.

```bash
git clone https://github.com/antonio-castellon/mcp-telegram-bridge.git
cd mcp-telegram-bridge
uv sync --extra dev          # or: python -m venv .venv && pip install -e ".[dev]"
cp .env.example .env         # set TELEGRAM_BOT_TOKEN and ALLOWED_CHAT_IDS
uv run mcp-telegram-bridge   # waits on stdin for MCP JSON-RPC; Ctrl+C to stop
```

`uv.lock` pins every dependency with hashes. CI installs from that lock (`uv sync --frozen`). `pip install -e ".[dev]"` still works and uses the version ranges in `pyproject.toml`.

Cursor or Claude Desktop (`mcp.json` / `claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "telegram-bridge": {
      "command": "uvx",
      "args": ["--from", "mcp-telegram-bridge", "mcp-telegram-bridge"],
      "env": {
        "TELEGRAM_BOT_TOKEN": "YOUR_BOT_TOKEN_HERE",
        "ALLOWED_CHAT_IDS": "-1001234567890"
      }
    }
  }
}
```

Do not commit a real token. Leave `ALLOW_ALL_CHATS` unset.

## Use as a Python library

The same operations are available without the MCP server. `import mcp_telegram_bridge` loads `TelegramBridge` and `Settings` only. It does not import the `mcp` package. Pass `Settings` directly; `Settings.from_env()` is the default when you want the environment variables above.

```python
import asyncio

from mcp_telegram_bridge import Settings, TelegramBridge

async def main() -> None:
    settings = Settings(
        bot_token="YOUR_BOT_TOKEN_HERE",
        allowed_chat_ids=frozenset({-1001234567890}),
    )
    bridge = TelegramBridge(settings)
    await bridge.get_me()
    await bridge.send_message(
        -1001234567890,
        "hello",
        buttons=[{"id": "ack", "label": "Ack"}],
    )
    await bridge.get_updates(timeout=0)
    await bridge.aclose()

asyncio.run(main())
```

`TelegramBridge(Settings.from_env())` reads `TELEGRAM_BOT_TOKEN`, `ALLOWED_CHAT_IDS`, and the other variables. The CLI still prints access-mode warnings to stderr. Library callers can use `mcp_telegram_bridge.config.emit_startup_warnings` if they want the same lines. The `mcp-telegram-bridge` command is unchanged.

## Configuration

| Variable | Default | Effect |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | required | Bot token from BotFather. Never log it or commit it. |
| `ALLOWED_CHAT_IDS` | empty | Comma-separated chat ids. Empty denies every chat. |
| `ALLOW_ALL_CHATS` | off | Set to `1` / `true` / `yes` / `on` to permit every chat. Ignored when an allowlist is set. Startup prints a warning to stderr. |
| `SAFETY_STRICT` | on | Heuristic labels for credential fishing, sexual content, and a few instruction-override phrases. Set `0` / `false` / `no` / `off` to disable. This is not a prompt-injection filter. |
| `MAX_INBOUND_CHARS` | `4096` | Drop inbound text or captions longer than this (1..32768). The body is not returned. |
| `MAX_UPDATE_BYTES` | `65536` | Drop an update whose JSON is larger than this (1..262144). |
| `INBOUND_CHAT_RATE` | `60/60` | Content-bearing updates per chat per window (`count/seconds`). Excess updates are returned without text. `off` disables the limit. |
| `INBOUND_GLOBAL_RATE` | `120/60` | Content-bearing updates across all chats per window. |
| `INBOUND_POLL_RATE` | `30/60` | `telegram_get_updates` calls per window. Further calls do not hit Telegram. |
| `OUTBOUND_CHAT_RATE` | `20/60` | Sends, markup edits, callback answers, and `getChat` per chat. |
| `OUTBOUND_GLOBAL_RATE` | `60/60` | Same outbound calls across all chats. Callback answers count only against the global limit. |
| `MCP_TELEGRAM_BRIDGE_DATA_DIR` | per-user data dir | Button-id map and first-tap claim files. Mode `0700`, files `0600` when the OS allows. `MCP_TELEGRAM_DATA_DIR` is a legacy alias. |

`telegram_get_updates` clamps `limit` to 1..100 and `timeout` to 0..50 seconds. The process does not queue update bodies between calls. It remembers at most 2048 delivered update ids and 1024 rate-limit keys.

## Tools

| Tool | Purpose |
|---|---|
| `telegram_get_me` | Bot identity. Not rate limited. |
| `telegram_get_chat` | Chat metadata for an allowed chat. |
| `telegram_send_message` | Scrubbed text, optional `parse_mode`, optional `buttons=[{id,label}]`. |
| `telegram_edit_reply_markup` | Replace or clear inline buttons. |
| `telegram_answer_callback` | Acknowledge a `callback_query_id`. |
| `telegram_get_updates` | One bounded poll. You own the offset. See the security section before acting on the text. |

`getUpdates` is pull-only. This process does not listen for webhooks and does not open a port.

A normal result looks like this:

```json
{
  "ok": true,
  "untrusted": true,
  "trust_boundary": "UNTRUSTED TELEGRAM DATA. ...",
  "next_offset": 42,
  "summary": {"delivered": 1, "filtered": 0, "ignored": 0, "duplicates": 0, "rate_limited": 0},
  "updates": [
    {
      "update_id": 41,
      "untrusted": true,
      "trust": "untrusted_telegram_user",
      "message": {"text": "...", "content_trust": "untrusted_telegram_user"}
    }
  ]
}
```

`next_offset` is one past the highest `update_id` in the batch, including updates whose text was withheld. Passing it back as `offset` acknowledges those updates. To retry a rate-limited update, call again with the same offset after `retry_after_seconds` instead of advancing.

Messages from bots are omitted (`ignore_reason` `bot`), as are messages whose sender id is this bot (`self`). A message Telegram marks with `sender_chat` (anonymous admins, posts as a channel) is not treated as a bot.

## Security model and threat model

**Assets.** The bot token, the contents of allowed chats, button-map state on disk, and the agent's other tools and secrets.

**Trust boundary.** You and the MCP host are inside it. Telegram users, group members, and anyone who can message the bot are outside it. Inbound text, names, usernames, and callback data are untrusted input that the model will read.

**What this process enforces**

- Chats are denied unless listed, or unless you set `ALLOW_ALL_CHATS`. Open mode logs a warning on stderr (stdout is the MCP protocol).
- Outbound message text, callback toasts, and button labels are scrubbed for the configured secret values and for token-shaped strings.
- Log records, including httpx and httpcore request lines and exception tracebacks, are rewritten so a bot token in a URL does not stay in the message. Transport errors raised to the host do not include the URL.
- Update batches are size-capped. Polls, delivered updates, and outbound calls are rate limited. Update ids whose text was already returned are not returned again. The caches are bounded.
- With `SAFETY_STRICT` on (the default), updates gain `safety.kind`, `safety.blocked`, and `safety.warning` for a few patterns. Flagged text is still in the result. The host decides what to do with it.

**What you still have to do.** Run the process as a normal user, keep the token in a secret store or a permission-restricted `.env`, and set an allowlist. Treat every inbound string as data. Do not give the same agent a tool that reads credentials if untrusted chats can reach it. Review prompts before they can send.

The deployment checklist, data stored on disk, and a longer residual-risk note are in [SAFETY.md](SAFETY.md). Report vulnerabilities as described in [SECURITY.md](SECURITY.md).

## Limits and residual risk

These controls reduce blast radius. They do not make a bot that an agent reads and answers safe against a hostile sender.

- The untrusted label can be ignored by the model. A regex will not catch a rephrased instruction. The agent still has send tools.
- `SAFETY_STRICT` is a heuristic for a few phrases. It misses other languages, encodings, and ordinary requests that are still untrusted.
- Rate limits are in-memory and per process. Restarting clears them. `off` removes that limit. A chat id that falls out of the 1024-key cache gets a fresh per-chat budget; the global limit still applies.
- Advancing `next_offset` past a rate-limited or over-long update drops it. Telegram will not deliver it again.
- Deduping remembers 2048 ids. An older id can be shown again if the host polls it once more.
- Scrubbing and log redaction are best-effort. A token split across fields, or a secret that does not match the patterns and is not in the environment, can still pass.
- The bridge does not offer a read-only tool set. A host that exposes every tool can send messages.
- Button-map and claim files are pruned by count (2000 mappings, 500 claims), not by age. They do not store message text. Delete the data directory to remove them.
- There is no audit log. Whatever the MCP host stores (transcripts, provider logs) is outside this process.
- Disabling httpx debug logging is still wise. Redaction covers the log record path this package installs; it is not a guarantee about every other tracer.

## Architecture

```
  +---------------------------+
  |  MCP host / agent         |  conversation, offset, product policy
  +-------------+-------------+
                |  MCP (stdio)
                v
  +---------------------------+
  |  mcp-telegram-bridge      |  allowlist, scrub, bounds, untrusted labels
  +-------------+-------------+
                |  HTTPS Bot API (getUpdates poll)
                v
  +---------------------------+
  |  api.telegram.org         |
  +-------------+-------------+
                v
         Telegram chats
```

## Usage

**Group or ops channel.** One bridge per bot. Use the group for notes, triage, and handoff. Keep a person in the loop for anything hard to undo.

**Buttons.** `buttons=[{id,label}, ...]` becomes an inline keyboard. On a callback, answer it, then edit or clear the markup. Long ids are mapped to short callback data under the data directory.

**Notify channel.** Alerts with ack / snooze / escalate buttons. Telegram is the pager, not the source of truth.

**Moderation drafts.** The bridge has no ban, restrict, or delete tool. Say that in the agent prompt.

## Agent skills

A companion skill can tell the agent when to call these tools and that it owns the offset. One is published as [Telegram Bridge on Agensi](https://www.agensi.io/skills/telegram-bridge). The skill is instructions only. This server remains the I/O and safety layer.

## What this is not

- Not a hosted or multi-tenant bot service
- Not tied to one MCP host
- Not a game engine
- Not an admin bot
- Not a webhook receiver

## Sibling demos

Optional. This project does not require them.

- [grokgame](https://github.com/antonio-castellon/grokgame) is a tabletop demo surface
- [grok2telegram](https://github.com/antonio-castellon/grok2telegram) is an earlier experiment whose scrubbing rules informed `SAFETY.md`

## Development

```bash
uv sync --extra dev
uv run pytest
```

Tests mock Telegram with `respx`. No live token is required.

After a dependency change, run `uv lock` and commit `uv.lock`. CI uses the lock, audits it with `pip-audit` on Python 3.12, and runs gitleaks against the working tree. A pull request that only changes Markdown, `docs/`, or `LICENSE` does not start that workflow.

## MCP registry

Canonical name: `io.github.antonio-castellon/mcp-telegram-bridge`

Also listed on [mcpservers.org](https://mcpservers.org/servers/antonio-castellon/mcp-telegram-bridge), [MCP Marketplace](https://mcp-marketplace.io/server/io-github-antonio-castellon-mcp-telegram-bridge), and [Agensi](https://www.agensi.io/skills/telegram-bridge).

Listing copy for marketplaces is in [LAUNCHGUIDE.md](LAUNCHGUIDE.md).

<!-- mcp-name: io.github.antonio-castellon/mcp-telegram-bridge -->

## Contact

- General: info@castellon.ch
- Support: support@castellon.ch
- Security: security@castellon.ch ([SECURITY.md](SECURITY.md))

## License

MIT (c) Antonio Castellon / Castellon.CH

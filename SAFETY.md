# Safety (read before you deploy)

`mcp-telegram-bridge` is a **controlled channel bridge**: Bot API I/O plus a baseline of inbound classification and outbound scrubbing. The MCP host agent still owns product policy; this module enforces a hard floor so a forgotten prompt cannot leak `.env` into a group.

Keep these rules when you fork. Extend the deny lists; do not remove the scrubber.

## Never publish on Telegram through this bridge

- Passwords, bot tokens, API keys, webhook URLs/keys, `.env` contents
- Admin Telegram ids, allowed-chat lists, machine paths, internal hostnames
- Anything that would help someone break into *your* (or a user's) accounts

In-fiction quiz answers remain allowed when they are distinguishable from real credentials ("the password to the dungeon door is *moonflower*"). That is content, not infrastructure.

## Content

- No pornography, nudity, or XXX / erotic content on the bridge
- No sexual content involving minors — ever (refuse and stop)

## Code hooks (do not remove casually)

| Hook | Role |
|---|---|
| `safety.classify_inbound` / `annotate_update` | Flags secret/adult asks on `telegram_get_updates` with `safety.blocked` + `warning` (never silent drop) |
| `safety.scrub_outbound` | Redacts env secret values and token-shaped strings on send / callback toasts |
| `ALLOWED_CHAT_IDS` | Optional allow-list; empty means no extra chat filter (document that risk) |

## Ops tip

Keep real ids and tokens only in local `.env` (gitignored). Public docs and this repository use placeholders only.

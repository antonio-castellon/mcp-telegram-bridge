# Connector safety

`mcp-telegram-bridge` is a narrow Telegram connector. Its threat model is accidental disclosure through an agent or a misconfigured deployment: credentials, internal identifiers, and traffic sent to the wrong chat. The bridge is not a content moderation system, DLP product, or substitute for Telegram account and host security.

## Transport and package posture

This server is **stdio-only** (launched by a local MCP host). It does not expose an HTTP/SSE/WebSocket MCP transport. Runtime dependency pin: `mcp>=1.27.2,<2` (clears CVE-2025-66416, CVE-2026-52869, CVE-2026-52870 ranges commonly flagged by scanners). We do not claim PyPI provenance attestation beyond what the published package and repository themselves provide; treat marketplace "PyPI verified" notes as informational for this stdio connector.

## Always-on hygiene

### Outbound scrubbing

All text sent through the bridge is scrubbed for configured environment values, common token shapes, secret-like environment assignments, and webhook URLs. This applies to message text, callback toasts, and button labels/ids. Scrubbing is a last-resort control, not permission to place secrets in prompts or logs. Do not put credentials in the repository, MCP configuration checked into source control, or Telegram messages.

### Chat allowlist

Set `ALLOWED_CHAT_IDS` to a comma-separated list of approved Telegram chat ids in deployments that should have bounded destinations. When set, send, edit, and chat-metadata tools reject other ids, and `telegram_get_updates` removes content from updates that are outside the list (or have no identifiable chat). An empty value disables this additional destination filter, so use it only when that exposure is intentional.

### Token handling

Keep `TELEGRAM_BOT_TOKEN` and other credentials in a local, permission-restricted `.env` or secret manager. Never commit `.env`, real chat ids, tokens, webhook keys, or internal host details. Rotate a token immediately if it is exposed.

### Button-map / claim data directory

Inline-button id mapping and `claim_message_tap` state are stored under a local data directory:

1. `MCP_TELEGRAM_BRIDGE_DATA_DIR` if set (preferred)
2. Legacy `MCP_TELEGRAM_DATA_DIR` if set
3. Otherwise a per-user data path (`platformdirs` when installed, else `$XDG_DATA_HOME` / `~/.local/share/mcp-telegram-bridge`, with `$XDG_CACHE_HOME` / `~/.cache` as a fallback)

The bridge creates that directory with mode `0o700` and writes state files with mode `0o600` when the filesystem honors POSIX modes (best-effort on Windows). Keep this directory on a local disk you control; do not point it at a shared or world-writable location.

## Optional strict inbound classification

Set `SAFETY_STRICT=1` (also `true`, `yes`, or `on`) to classify inbound update text for credential fishing involving passwords, tokens, webhooks, admin internals, and for NSFW content. In strict mode, `telegram_get_updates` adds `safety.kind`, `safety.blocked`, and `safety.warning` fields; flagged updates remain visible so the MCP host can decide how to handle them.

Strict mode is **off by default**. With it off, the classifier is not run and updates are returned without secret/NSFW blocking fields. Always-on scrubbing and the chat allowlist still apply. Enable strict mode for public or otherwise untrusted groups when the additional heuristic signal is useful, and treat it as advisory rather than a complete filter.

## Operational responsibility

The MCP host owns conversation and product policy. Review prompts, logs, button data, and deployment permissions; use HTTPS and a restricted runtime; and keep human approval for irreversible Telegram administration.

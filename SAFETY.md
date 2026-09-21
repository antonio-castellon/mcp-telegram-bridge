# Connector safety

`mcp-telegram-bridge` is a narrow Telegram connector. Its threat model is accidental disclosure through an agent or a misconfigured deployment: credentials, internal identifiers, and traffic sent to the wrong chat. The bridge is not a content moderation system, DLP product, or substitute for Telegram account and host security.

## Always-on hygiene

### Outbound scrubbing

All text sent through the bridge is scrubbed for configured environment values, common token shapes, secret-like environment assignments, and webhook URLs. This applies to message text, callback toasts, and button labels/ids. Scrubbing is a last-resort control, not permission to place secrets in prompts or logs. Do not put credentials in the repository, MCP configuration checked into source control, or Telegram messages.

### Chat allowlist

Set `ALLOWED_CHAT_IDS` to a comma-separated list of approved Telegram chat ids in deployments that should have bounded destinations. When set, send, edit, and chat-metadata tools reject other ids, and `telegram_get_updates` removes content from updates that are outside the list (or have no identifiable chat). An empty value disables this additional destination filter, so use it only when that exposure is intentional.

### Token handling

Keep `TELEGRAM_BOT_TOKEN` and other credentials in a local, permission-restricted `.env` or secret manager. Never commit `.env`, real chat ids, tokens, webhook keys, or internal host details. Rotate a token immediately if it is exposed.

## Optional strict inbound classification

Set `SAFETY_STRICT=1` (also `true`, `yes`, or `on`) to classify inbound update text for credential fishing involving passwords, tokens, webhooks, admin internals, and for NSFW content. In strict mode, `telegram_get_updates` adds `safety.kind`, `safety.blocked`, and `safety.warning` fields; flagged updates remain visible so the MCP host can decide how to handle them.

Strict mode is **off by default**. With it off, the classifier is not run and updates are returned without secret/NSFW blocking fields. Always-on scrubbing and the chat allowlist still apply. Enable strict mode for public or otherwise untrusted groups when the additional heuristic signal is useful, and treat it as advisory rather than a complete filter.

## Operational responsibility

The MCP host owns conversation and product policy. Review prompts, logs, button data, and deployment permissions; use HTTPS and a restricted runtime; and keep human approval for irreversible Telegram administration.

# Security policy

## Contact

Report a vulnerability privately. Do not open a public issue, and do not include a live bot token or other secret.

- Email: security@castellon.ch
- Or a private advisory: https://github.com/antonio-castellon/mcp-telegram-bridge/security/advisories

General questions: info@castellon.ch. Help using the bridge: support@castellon.ch.

## Supported versions

| Version | Security fixes |
|---|---|
| 0.2.x | Supported |
| 0.1.x | Not supported |

0.2.0 is the first release that denies every chat when `ALLOWED_CHAT_IDS` is empty. Earlier releases treat an empty allowlist as allow-all. Upgrade before you rely on admission control.

## What to send

- The version (`mcp-telegram-bridge` version and the commit if you are running from a checkout)
- What you observed and what an attacker would gain
- Whether the default configuration is affected
- The MCP host you used, if it matters

Do not send the token, a `.env` file, or a transcript that contains one. If you already exposed a token, revoke it at BotFather first.

## What happens next

You will get a reply confirming the report was received. If a fix is needed, it lands in this repository before public discussion of the details. There is no bounty program and no fixed response-time promise.

A skipped allowlist check, outbound scrubbing that misses a token the scrubber claims to remove, or a log line that still contains the bot token are in scope. A model obeying untrusted Telegram text is a residual risk of this design; see [SAFETY.md](SAFETY.md). Reports of that class are still welcome when they show a control in this repository that does not do what it documents.

## Secrets in the tree

Do not commit tokens, real chat dumps, or `.env`. CI runs gitleaks on the working tree for changes that are not documentation-only. The initial commit contains synthetic fixtures that were removed from the tree; do not copy them back.

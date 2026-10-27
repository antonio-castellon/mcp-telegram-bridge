# Changelog

## 0.2.0

Breaking admission change and abuse controls for the stdio bridge.

### Security

- An empty `ALLOWED_CHAT_IDS` denies every chat. `ALLOW_ALL_CHATS=1` is the explicit opt-in for open mode, and startup prints a warning to stderr. A non-empty allowlist wins over open mode.
- Bot tokens are redacted from log records, including httpx and httpcore URLs and exception tracebacks. Transport errors no longer carry the request URL.
- Inbound polls are bounded: `limit` 1..100, `timeout` 0..50, maximum text length, maximum update size, per-chat and global content rates, and a poll rate. Outbound sends, edits, callback answers, and `getChat` are rate limited.
- Messages from bots and from this bot are ignored. Update ids whose text was already returned are not returned again. Both caches are size-capped.
- `telegram_get_updates` labels inbound text as untrusted. `SAFETY_STRICT` defaults to on and adds an advisory hit for a few instruction-override phrases. The classifier remains a heuristic.

### Supply chain

- `uv.lock` pins dependencies with hashes. CI installs with `uv sync --frozen`.
- GitHub Actions are pinned to commit SHAs. Permissions stay at `contents: read`.
- Dependabot watches the lockfile and Actions. CI runs `pip-audit` and gitleaks. Documentation-only changes do not start the workflow.

### Documentation

- README quick start, configuration table, threat model, and residual risks.
- `SAFETY.md` is the deployment and hardening guide.
- `SECURITY.md` lists security@castellon.ch, supported versions, and the disclosure process.
- Package contact is info@castellon.ch. Support is support@castellon.ch.

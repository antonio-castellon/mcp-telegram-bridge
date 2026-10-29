# Security model and hardening

Operational guide for running `mcp-telegram-bridge`. The configuration table lives in the [README](README.md). How to report a vulnerability is in [SECURITY.md](SECURITY.md).

This is a narrow Telegram connector. It is not a content-moderation product, a data-loss-prevention suite, or a substitute for Telegram's own account controls.

## Threat model

The process is a stdio MCP server. An agent on the same machine reads tool results and may call send tools. People on Telegram are untrusted. A hostile sender's success looks like this: their text is copied into the model context, the model treats it as an instruction, and a send tool delivers something you did not mean to send (or the model reveals something it can see).

| Boundary | Inside | Outside |
|---|---|---|
| Process | MCP host, this server, the data directory | Telegram, other users, other hosts |
| Network | Outbound HTTPS to `api.telegram.org` | No listening port, no webhook |
| Chats | Ids in `ALLOWED_CHAT_IDS` | Every other chat, unless `ALLOW_ALL_CHATS` is on |
| Tool results | Labels this server adds | The text those labels describe |

Assets worth protecting: the bot token, messages in allowed chats, the button-map files, and any other secret the agent can see.

## Deployment checklist

1. Run the bridge as your own user, not as root, on a machine you administer.
2. Put `TELEGRAM_BOT_TOKEN` in a secret manager or a `.env` that only that user can read. `.env` is gitignored. Do not put the token in `mcp.json` if that file is committed.
3. Set `ALLOWED_CHAT_IDS` to the chats that may use the bot. An empty value denies every chat. That is intentional.
4. Leave `ALLOW_ALL_CHATS` unset. If you set it, the process prints a warning to stderr at startup and every chat the bot can see is permitted. A non-empty allowlist overrides open mode, and the warning says so.
5. Leave `SAFETY_STRICT` at its default (`on`) unless you have a reason to hide the heuristic labels. Read the residual-risk section before you turn it off.
6. Keep the default rate limits unless you have measured a real backlog. Tightening them is safer than setting them to `off`.
7. Point `MCP_TELEGRAM_BRIDGE_DATA_DIR` at a local directory on a disk you control, not at a shared or world-writable path.
8. Do not publish the stdio process. Do not put an HTTP reverse proxy in front of it. There is nothing to proxy.
9. Rotate the token at BotFather if it appears in a log, a transcript, a commit, or a chat.
10. Confirm stderr, not only stdout. The MCP protocol uses stdout. Warnings must not be mixed into it.

A send to a chat that is not listed raises `PermissionError` and does not call Telegram. The same happens for every chat when the allowlist is empty and open mode is off.

## Access control

`chat_allowed` is fail-closed:

- Allowlist non-empty: only those ids pass. `ALLOW_ALL_CHATS` does not widen it.
- Allowlist empty and `ALLOW_ALL_CHATS` off: nothing passes. Sends raise `PermissionError`. Updates come back as `filtered` stubs with no message body.
- Allowlist empty and `ALLOW_ALL_CHATS` on: every chat passes, including an update with no chat id. Stderr gets a warning.

`telegram_get_me` does not take a chat id. The other tools do, except `telegram_answer_callback`, which has only a callback id and is covered by the global outbound rate limit.

## Token handling

The Bot API requires the token in the URL path (`/bot<token>/<method>`). httpx logs that URL at info level, and httpcore can log it at debug level. Importing this package installs a log-record factory that rewrites records before handlers see them:

- exact token values registered at startup, when they are at least 16 characters
- the same value with the colon percent-encoded
- bot-token shapes and a few other well-known token shapes

`TelegramError` does not include the request URL. HTTP error bodies are truncated and passed through the same redactor.

Do not turn on a custom tracer that copies `request.url` into a side channel that bypasses `logging`. Prefer leaving httpx logging at warning or above anyway. Scrubbing of outbound text is a last resort for the same class of mistake: configured environment values, token-shaped strings, secret-like assignments, and webhook URLs are replaced before `sendMessage` and callback toasts. It is not permission to put secrets in prompts.

## Abuse controls

There is no background queue. Each `telegram_get_updates` call is one poll:

- `limit` is clamped to 1..100 and `timeout` to 0..50. The HTTP read timeout is 30 seconds plus that poll timeout, and the client default remains 90 seconds for other methods.
- Text and captions longer than `MAX_INBOUND_CHARS`, and updates larger than `MAX_UPDATE_BYTES`, are replaced with a filtered stub. The stub's reason does not echo the text.
- `INBOUND_POLL_RATE` limits how often the tool calls Telegram. When it trips, the result is `ok: false`, `rate_limited: true`, and Telegram is not called.
- `INBOUND_CHAT_RATE` and `INBOUND_GLOBAL_RATE` limit how many updates are returned with their text. Excess updates keep `update_id` and set `rate_limited`, so you can see that something was withheld.
- `OUTBOUND_CHAT_RATE` and `OUTBOUND_GLOBAL_RATE` limit sends, markup edits, callback answers, and `getChat`. The tool raises `RateLimitExceeded` and does not call Telegram.
- Update ids are remembered only after their content was returned, up to 2048 ids. A later poll of the same id is a `duplicate` stub without the text. Ignored and filtered updates are evaluated again, so a rate limit can clear if you reuse the same offset.
- Senders with `from.is_bot` are ignored, and so is `from.id` equal to this bot's id from `getMe`. Messages that carry `sender_chat` are kept: Telegram uses that shape for anonymous admins and channel identities, and dropping them would hide human posts.

Rejected rate-limit attempts are not stored, so a retry works once the window moves. The per-chat map keeps at most 1024 keys.

`getMe` is not rate limited, so a connectivity check still works when the outbound budget is spent. It is also how the process learns its own user id. If `getMe` fails, bot messages are still ignored via `is_bot`, and the failure is not logged with the exception text (that text can contain the URL).

## Untrusted inbound text

Every `telegram_get_updates` result includes `untrusted: true` and a `trust_boundary` string. Delivered messages set `content_trust` to `untrusted_telegram_user`. The text itself is not rewritten, so a host can still read `message.text`.

`SAFETY_STRICT` defaults to on. It adds:

| `safety.kind` | Meaning |
|---|---|
| `ok` | No heuristic hit |
| `secrets` | Looks like a request for tokens, passwords, or host details |
| `adult` | Sexual or NSFW wording in the built-in list |
| `injection` | A small set of "ignore previous instructions" style phrases |
| `policy` | Withheld because of the allowlist, size, or rate limit |

`blocked: true` means the heuristic fired or the update was withheld. The text of a delivered update is still present. Turning strict mode off removes these labels. It does not make the text trusted. The untrusted marker stays.

## Data on disk

Inline-button ids that do not fit in 64 bytes, and first-tap claim records, are stored under the data directory:

1. `MCP_TELEGRAM_BRIDGE_DATA_DIR` if set
2. `MCP_TELEGRAM_DATA_DIR` if set
3. Otherwise a per-user path (`platformdirs` when installed, else `$XDG_DATA_HOME/mcp-telegram-bridge` or `~/.local/share/mcp-telegram-bridge`, with the XDG cache home as a fallback)

The directory is created mode `0700` and files mode `0600` when the filesystem honors POSIX modes. The map keeps 2000 entries and the claim index keeps 500, dropping the oldest. There is no time-based purge and no message-content log. Removing the directory deletes the state.

Nothing in this process is an audit trail. The host's transcripts are the host's responsibility.

## Supply chain

Runtime dependencies are `mcp>=2.3.0,<3` (above the 2.x releases affected by GHSA-84m7-p3x7-pcfv, unbounded Streamable HTTP session retention, fixed in 2.2.0; this server does not use that transport), `httpx`, and `pydantic`. `uv.lock` records hashes. GitHub Actions are pinned to commit SHAs. Dependabot opens grouped weekly updates for the lockfile and for Actions. CI runs `pip-audit` and gitleaks on non-documentation changes. A docs-only pull request does not run that workflow, so do not paste secrets into Markdown.

## If a token leaks

1. Revoke it in BotFather and create a new one.
2. Update the secret store and restart the host so the old process is gone.
3. Treat chats and host transcripts from that period as exposed.
4. If the leak was in this repository, use the contact in [SECURITY.md](SECURITY.md). Do not open a public issue that contains the token.

## Residual risk

Read this before exposing the bot to people you do not know.

The model sees untrusted text and may follow it. Labels and a short list of phrases do not fix that. A sender can ask for a tool call in words the regex does not use. The safe deployment is a small allowlist, a host prompt that refuses instructions from Telegram text, and a human on irreversible actions.

Outbound scrubbing and log redaction miss secrets that are not in the environment and do not look like the known shapes. They also cannot see a tracer that reads the httpx request object directly.

Rate limits reset on restart and can be turned off. They are sized for one agent talking to a few chats, not for a public bot that must survive a flood while answering everyone. A full poll can still deliver up to the global content budget in one call.

There is no read-only mode, no per-tool scope, and no budget that counts model tokens. Those belong in the host.

Allowing all chats, or adding a public group to the allowlist, accepts the prompt-injection exposure above. The startup warning is a reminder, not a control.

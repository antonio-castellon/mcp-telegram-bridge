# Contributing

mcp-telegram-bridge is small on purpose. The agent owns the conversation. This process does Bot API I/O, outbound scrubbing, and fail-closed chat admission. A change that adds a game loop, an inbox, or a second tool for the same job does not fit, even if it is well made.

A bug you can reproduce, a missing test, or a tighter safety check does fit.

Questions about using the bridge: support@castellon.ch. Security reports: security@castellon.ch (see SECURITY.md). Everything else: info@castellon.ch.

To propose a change:

1. Open an issue first if the problem or the approach is not clear yet.
2. Branch from `main`.
3. Do not commit secrets, bot tokens, or `.env` files. Scan the diff before you commit.
4. If you change a dependency, run `uv lock` and commit `uv.lock`. CI installs with `uv sync --frozen`.
5. Tests must stay green. `uv sync --extra dev` then `uv run pytest`.
6. Keep the change small. Empty allowlists stay deny-all. Do not weaken that without an explicit opt-in and a test.

A pull request that only touches Markdown, `docs/`, or `LICENSE` does not run CI. Do not put secrets in those files. Any other change runs the tests, `pip-audit`, and gitleaks.

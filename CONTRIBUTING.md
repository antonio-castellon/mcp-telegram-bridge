# Contributing

mcp-telegram-bridge is small on purpose. The agent owns the conversation. This process does Bot API I/O, outbound scrubbing, and chat allowlisting. A change that adds a game loop, an inbox, or a second tool for the same job does not fit, even if it is well made.

A bug you can reproduce, a missing test, or a tighter safety check does fit.

To propose a change:

1. Open an issue first if the problem or the approach is not clear yet.
2. Branch from `main`.
3. Do not commit secrets, bot tokens, or `.env` files.
4. Tests and CI must stay green.
5. Keep the change small and safe: read-only by default, and allowlists for destinations.

Python 3.11 or newer. `pip install -e ".[dev]"` and then `pytest`.

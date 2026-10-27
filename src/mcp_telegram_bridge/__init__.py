"""Telegram bridge library and, separately, a stdio MCP server.

Importing this package does not import the MCP SDK. The server lives in
``mcp_telegram_bridge.server`` and is what the ``mcp-telegram-bridge`` command runs.
"""

from __future__ import annotations

from .bridge import RateLimitExceeded, TelegramBridge
from .config import Settings

__version__ = "0.2.1"

__all__ = ["RateLimitExceeded", "Settings", "TelegramBridge", "__version__"]

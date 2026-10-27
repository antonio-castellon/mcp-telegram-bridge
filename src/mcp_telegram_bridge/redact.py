"""Redact bot tokens from log records, tracebacks, and error text.

Telegram puts the bot token in the request path. httpx and httpcore log that
URL at info/debug level, so a logging filter has to run for every record, not
only for messages this package builds itself.
"""

from __future__ import annotations

import logging
import re
import traceback
from typing import Iterable
from urllib.parse import quote

# Bot API tokens and the same tokens with the colon percent-encoded.
_BOT_TOKEN = re.compile(
    r"(?i)\d{6,}:[A-Za-z0-9_-]{20,}|\d{6,}%3[aA][A-Za-z0-9_-]{20,}"
)
_GENERIC_SECRET = re.compile(
    r"(?x)\b(?:"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"sk-[A-Za-z0-9]{20,}"
    r")\b"
)

_MIN_EXACT = 16
_tokens: list[str] = []
_installed = False
_original_factory = logging.getLogRecordFactory()


def redact_text(text: str, tokens: Iterable[str] | None = None) -> str:
    """Remove known tokens and token-shaped strings from ``text``."""
    if not text:
        return text
    for token in list(tokens or ()) + _tokens:
        if not token or len(token) < _MIN_EXACT:
            continue
        if token in text:
            text = text.replace(token, "[REDACTED]")
        encoded = quote(token, safe="")
        if encoded and encoded != token and encoded in text:
            text = text.replace(encoded, "[REDACTED]")
    text = _BOT_TOKEN.sub("[REDACTED]", text)
    text = _GENERIC_SECRET.sub("[REDACTED]", text)
    return text


def _render(record: logging.LogRecord) -> str:
    try:
        return record.getMessage()
    except Exception:
        return " ".join(part for part in (str(record.msg), str(record.args)) if part)


def _redact_record(record: logging.LogRecord) -> None:
    redacted = redact_text(_render(record))
    record.msg = redacted
    record.args = ()
    record.message = redacted
    if record.exc_info:
        formatted = "".join(traceback.format_exception(*record.exc_info))
        record.exc_text = redact_text(formatted)
        record.exc_info = None
    elif isinstance(record.exc_text, str):
        record.exc_text = redact_text(record.exc_text)
    stack = getattr(record, "stack_info", None)
    if isinstance(stack, str) and stack:
        record.stack_info = redact_text(stack)


def install_log_redaction(token: str | None = None) -> None:
    """Install a process-wide log-record factory that redacts tokens.

    Safe to call more than once. Later tokens are added to the exact-match
    list; the generic bot-token pattern is always applied.
    """
    global _installed
    if token and len(token) >= _MIN_EXACT and token not in _tokens:
        _tokens.append(token)
    if _installed:
        return

    def factory(*args, **kwargs):
        record = _original_factory(*args, **kwargs)
        _redact_record(record)
        return record

    logging.setLogRecordFactory(factory)
    _installed = True


# Active as soon as this module loads, before the first Bot API call.
install_log_redaction(None)

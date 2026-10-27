"""Bot tokens must not survive log records or error text."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx
import pytest

from mcp_telegram_bridge.redact import install_log_redaction, redact_text
from mcp_telegram_bridge.telegram import TelegramClient, TelegramError
from mcp_telegram_bridge.config import Settings


def _token() -> str:
    return f"{'8' * 9}:{'B' * 32}"


def test_redact_text_covers_raw_and_percent_encoded_forms():
    token = _token()
    encoded = quote(token, safe="")
    text = f"https://api.telegram.org/bot{token}/getMe and {encoded}"
    redacted = redact_text(text, [token])
    assert token not in redacted
    assert encoded not in redacted
    assert "B" * 32 not in redacted
    assert "[REDACTED]" in redacted


def test_log_records_and_tracebacks_drop_the_token(caplog):
    token = _token()
    install_log_redaction(token)
    caplog.set_level(logging.DEBUG)
    logging.getLogger("httpx").info(
        "HTTP Request: POST https://api.telegram.org/bot%s/getMe",
        token,
    )
    logging.getLogger("httpcore.http11").debug("send %s", quote(token, safe=""))
    try:
        raise RuntimeError(f"failed for bot{token}")
    except RuntimeError:
        logging.getLogger("httpx").exception("transport")
    assert token not in caplog.text
    assert "B" * 32 not in caplog.text
    assert "[REDACTED]" in caplog.text


@pytest.mark.asyncio
async def test_httpx_info_log_during_request_hides_token(caplog):
    token = _token()

    def handler(request: httpx.Request) -> httpx.Response:
        assert token in str(request.url)
        return httpx.Response(200, json={"ok": True, "result": {"id": 1, "is_bot": True}})

    caplog.set_level(logging.DEBUG, logger="httpx")
    caplog.set_level(logging.DEBUG, logger="httpcore")
    settings = Settings(bot_token=token, api_base="https://api.telegram.org")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TelegramClient(settings, client=http)
        me = await client.get_me()
    assert me["id"] == 1
    assert token not in caplog.text
    assert "B" * 32 not in caplog.text


@pytest.mark.asyncio
async def test_transport_error_does_not_include_token():
    token = _token()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    settings = Settings(bot_token=token, api_base="https://api.telegram.org")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = TelegramClient(settings, client=http)
        with pytest.raises(TelegramError) as caught:
            await client.get_me()
    message = str(caught.value)
    assert token not in message
    assert "B" * 32 not in message
    assert "request failed" in message

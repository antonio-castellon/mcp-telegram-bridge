"""HTTP error context for TelegramClient.call."""

from __future__ import annotations

import httpx
import pytest
import respx

from mcp_telegram_bridge.config import Settings
from mcp_telegram_bridge.telegram import TelegramClient, TelegramError


@pytest.mark.asyncio
@respx.mock
async def test_call_http_error_includes_method_status_body_not_token():
    token = "123456:AA-SECRET-TOKEN-VALUE-SHOULD-NOT-LEAK"
    settings = Settings(bot_token=token, api_base="https://api.telegram.org")
    route = respx.post(url__regex=r".*/bot.*/getMe$").mock(
        return_value=httpx.Response(401, text='{"description":"Unauthorized"}')
    )
    client = TelegramClient(settings)
    with pytest.raises(TelegramError) as ei:
        await client.get_me()
    err = ei.value
    msg = str(err)
    assert err.method == "getMe"
    assert "401" in msg
    assert "Unauthorized" in msg
    assert token not in msg
    assert "SECRET" not in msg
    assert route.called
    await client.aclose()

"""HTTP error context and timeouts for TelegramClient.call."""

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


@pytest.mark.asyncio
async def test_call_keeps_the_client_timeout():
    """Passing timeout=None to httpx disables the timeout. Do not do that."""
    reads: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        reads.append(float(request.extensions["timeout"]["read"]))
        return httpx.Response(200, json={"ok": True, "result": {"id": 1, "is_bot": True}})

    settings = Settings(bot_token="t", api_base="https://api.telegram.org")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=httpx.Timeout(90.0, connect=15.0),
    ) as http:
        client = TelegramClient(settings, client=http)
        await client.get_me()
        await client.get_updates(limit=1, timeout=10)
    assert reads == [90.0, 40.0]

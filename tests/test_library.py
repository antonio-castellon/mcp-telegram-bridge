"""Public library API, without the MCP server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
import respx

from mcp_telegram_bridge import Settings, TelegramBridge
from mcp_telegram_bridge.bridge import RateLimitExceeded

TOKEN = f"{'4' * 9}:{'E' * 32}"
API = f"https://api.telegram.org/bot{TOKEN}"


def test_import_does_not_load_mcp():
    script = """
import sys
import mcp_telegram_bridge
from mcp_telegram_bridge import Settings, TelegramBridge
bridge = TelegramBridge(Settings(bot_token="t", allowed_chat_ids=frozenset({1})))
assert bridge.settings.chat_allowed(1)
loaded = [name for name in sys.modules if name == "mcp" or name.startswith("mcp.")]
assert loaded == [], loaded
"""
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 0, result.stderr


def test_programmatic_settings_do_not_read_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "1")
    monkeypatch.setenv("ALLOW_ALL_CHATS", "1")
    monkeypatch.setenv("SAFETY_STRICT", "0")
    settings = Settings(
        bot_token="t",
        allowed_chat_ids=frozenset({5}),
        data_dir=tmp_path,
    )
    assert settings.chat_allowed(5) is True
    assert settings.chat_allowed(1) is False
    assert settings.allow_all_chats is False
    assert settings.safety_strict is True
    from_env = Settings.from_env()
    assert from_env.chat_allowed(1) is True
    assert from_env.allow_all_chats is True
    assert from_env.safety_strict is False


@pytest.mark.asyncio
@respx.mock
async def test_library_send_scrubs_and_rejects(tmp_path: Path, monkeypatch):
    secret = f"{'6' * 10}:{'Q' * 32}"
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", secret)
    route = respx.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"message_id": 3}})
    )
    bridge = TelegramBridge(
        Settings(bot_token=TOKEN, allowed_chat_ids=frozenset({9}), data_dir=tmp_path)
    )
    with pytest.raises(PermissionError):
        await bridge.send_message(8, "nope")
    assert route.call_count == 0
    sent = await bridge.send_message(
        9,
        f"token is {secret}",
        buttons=[{"id": "ack", "label": "Ack"}],
    )
    assert sent["scrubbed"] is True
    body = json.loads(route.calls.last.request.content.decode())
    assert secret not in body["text"]
    assert "[REDACTED]" in body["text"]
    assert body["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "ack"
    await bridge.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_library_get_updates_filters_bots_and_dedupes(tmp_path: Path):
    respx.post(f"{API}/getMe").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": {"id": 50, "is_bot": True}})
    )
    respx.post(f"{API}/getUpdates").mock(
        return_value=httpx.Response(
            200,
            json={
                "ok": True,
                "result": [
                    {
                        "update_id": 1,
                        "message": {
                            "message_id": 1,
                            "chat": {"id": 9},
                            "from": {"id": 3, "is_bot": True},
                            "text": "bot-body",
                        },
                    },
                    {
                        "update_id": 2,
                        "message": {
                            "message_id": 2,
                            "chat": {"id": 9},
                            "from": {"id": 4, "is_bot": False},
                            "text": "human-body",
                        },
                    },
                ],
            },
        )
    )
    bridge = TelegramBridge(
        Settings(
            bot_token=TOKEN,
            allowed_chat_ids=frozenset({9}),
            safety_strict=False,
            data_dir=tmp_path,
        )
    )
    first = await bridge.get_updates(timeout=0)
    assert first["summary"]["ignored"] == 1
    assert first["summary"]["delivered"] == 1
    assert first["updates"][1]["message"]["text"] == "human-body"
    assert first["updates"][1]["untrusted"] is True
    assert "bot-body" not in json.dumps(first)
    second = await bridge.get_updates(timeout=0)
    assert second["updates"][1]["duplicate"] is True
    assert "human-body" not in json.dumps(second["updates"])
    await bridge.aclose()


@pytest.mark.asyncio
@respx.mock
async def test_library_outbound_rate_limit(tmp_path: Path):
    respx.post(f"{API}/answerCallbackQuery").mock(
        return_value=httpx.Response(200, json={"ok": True, "result": True})
    )
    bridge = TelegramBridge(
        Settings(
            bot_token=TOKEN,
            allowed_chat_ids=frozenset({9}),
            outbound_global_rate=(1, 60.0),
            data_dir=tmp_path,
        )
    )
    assert (await bridge.answer_callback("cq", text="ok"))["ok"] is True
    with pytest.raises(RateLimitExceeded):
        await bridge.answer_callback("cq2")
    await bridge.aclose()

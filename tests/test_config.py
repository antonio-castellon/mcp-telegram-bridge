"""Access-mode and limit configuration."""

from __future__ import annotations

import io

import pytest

from mcp_telegram_bridge.config import (
    Settings,
    emit_startup_warnings,
    startup_warnings,
)


def _token() -> str:
    return f"{'3' * 9}:{'C' * 32}"


def test_empty_allowlist_denies_every_chat():
    settings = Settings(bot_token="t")
    assert settings.chat_allowed(1) is False
    assert settings.chat_allowed(-100) is False
    assert settings.open_mode is False
    assert settings.has_chat_filter is True


def test_allowlist_admits_only_listed_chats():
    settings = Settings(bot_token="t", allowed_chat_ids=frozenset({5, -8}))
    assert settings.chat_allowed(5) is True
    assert settings.chat_allowed(6) is False


def test_open_mode_is_explicit_and_allowlist_wins():
    open_mode = Settings(bot_token="t", allow_all_chats=True)
    assert open_mode.chat_allowed(99) is True
    assert open_mode.open_mode is True
    both = Settings(
        bot_token="t",
        allow_all_chats=True,
        allowed_chat_ids=frozenset({5}),
    )
    assert both.open_mode is False
    assert both.chat_allowed(5) is True
    assert both.chat_allowed(6) is False


def test_from_env_fail_closed_and_open_opt_in(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.delenv("ALLOWED_CHAT_IDS", raising=False)
    monkeypatch.delenv("ALLOW_ALL_CHATS", raising=False)
    closed = Settings.from_env()
    assert closed.chat_allowed(1) is False
    assert closed.safety_strict is True
    monkeypatch.setenv("ALLOW_ALL_CHATS", "yes")
    opened = Settings.from_env()
    assert opened.chat_allowed(1) is True
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "4, 5")
    listed = Settings.from_env()
    assert listed.chat_allowed(4) is True
    assert listed.chat_allowed(9) is False
    assert listed.allow_all_chats is True
    assert listed.open_mode is False


def test_from_env_rejects_bad_allowlist_and_rates(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "nope")
    with pytest.raises(RuntimeError, match="ALLOWED_CHAT_IDS"):
        Settings.from_env()
    monkeypatch.setenv("ALLOWED_CHAT_IDS", "")
    monkeypatch.setenv("INBOUND_CHAT_RATE", "lots")
    with pytest.raises(RuntimeError, match="INBOUND_CHAT_RATE"):
        Settings.from_env()
    monkeypatch.setenv("INBOUND_CHAT_RATE", "off")
    monkeypatch.setenv("MAX_INBOUND_CHARS", "999999")
    with pytest.raises(RuntimeError, match="MAX_INBOUND_CHARS"):
        Settings.from_env()


def test_from_env_rate_off_disables_limit(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("OUTBOUND_GLOBAL_RATE", "0")
    monkeypatch.setenv("INBOUND_POLL_RATE", "15/30")
    settings = Settings.from_env()
    assert settings.outbound_global_rate is None
    assert settings.inbound_poll_rate == (15, 30.0)


def test_startup_warnings_cover_each_access_mode_and_hide_the_token():
    token = _token()
    closed = Settings(bot_token=token)
    opened = Settings(bot_token=token, allow_all_chats=True)
    both = Settings(bot_token=token, allow_all_chats=True, allowed_chat_ids=frozenset({1}))
    quiet = Settings(bot_token=token, allowed_chat_ids=frozenset({1}))
    assert "ALLOW_ALL_CHATS is off" in startup_warnings(closed)[0]
    assert "Every chat is permitted" in startup_warnings(opened)[0]
    assert "open mode is not used" in startup_warnings(both)[0]
    assert startup_warnings(quiet) == []
    buffer = io.StringIO()
    emit_startup_warnings(opened, buffer)
    text = buffer.getvalue()
    assert "mcp-telegram-bridge:" in text
    assert token not in text
    assert "C" * 32 not in text

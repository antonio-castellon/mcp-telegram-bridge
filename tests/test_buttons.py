"""Inline keyboard + claim_message_tap tests."""

from __future__ import annotations

import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from mcp_telegram_bridge import buttons as btn


def test_normalize_and_build_keyboard(tmp_path: Path):
    specs = btn.normalize_buttons(
        [{"id": "ack", "label": "Ack"}, {"id": "snooze", "text": "Snooze"}]
    )
    assert specs[1]["label"] == "Snooze"
    markup = btn.build_inline_keyboard(specs, chat_id=-100, data_dir=tmp_path, row_width=2)
    rows = markup["inline_keyboard"]
    assert len(rows) == 1
    assert rows[0][0]["callback_data"] == "ack"
    assert rows[0][1]["text"] == "Snooze"


def test_long_id_mapped_and_resolved(tmp_path: Path):
    long_id = "x" * 80
    markup = btn.build_inline_keyboard(
        [{"id": long_id, "label": "Go"}],
        chat_id=42,
        data_dir=tmp_path,
    )
    cb = markup["inline_keyboard"][0][0]["callback_data"]
    assert cb.startswith("t:")
    assert len(cb.encode()) <= btn.CALLBACK_DATA_MAX
    assert btn.resolve_callback_data(tmp_path, 42, cb) == long_id


def test_parse_buttons_arg():
    assert btn.parse_buttons_arg("a:One|b:Two") == [
        {"id": "a", "label": "One"},
        {"id": "b", "label": "Two"},
    ]
    with pytest.raises(ValueError):
        btn.parse_buttons_arg("nocolon")


def test_claim_message_tap_first_wins(tmp_path: Path):
    assert btn.claim_message_tap(tmp_path, 1, 99, verb="ack", uid=7) is True
    assert btn.claim_message_tap(tmp_path, 1, 99, verb="ack", uid=8) is False
    assert btn.claim_message_tap(tmp_path, 1, 100, verb="ack", uid=8) is True


def test_claim_message_tap_atomic_under_contention(tmp_path: Path):
    """Exactly one of many concurrent claims for the same message should win."""
    winners: list[bool] = []
    barrier = threading.Barrier(16)

    def once(uid: int) -> bool:
        barrier.wait(timeout=5)
        return btn.claim_message_tap(tmp_path, 7, 42, verb="ack", uid=uid)

    with ThreadPoolExecutor(max_workers=16) as pool:
        winners = list(pool.map(once, range(16)))
    assert sum(1 for w in winners if w) == 1
    assert sum(1 for w in winners if not w) == 15
    sentinel = tmp_path / "claims" / "7_42.claimed"
    assert sentinel.is_file()


def test_data_dir_permissions_when_supported(tmp_path: Path):
    btn.claim_message_tap(tmp_path, 1, 2, verb="ack", uid=1)
    mode = stat.S_IMODE(tmp_path.stat().st_mode)
    # On POSIX, expect owner rwx only; skip strict assert on non-POSIX semantics.
    if os.name == "posix":
        assert mode & 0o077 == 0
        claim = tmp_path / "callback_claimed.json"
        fmode = stat.S_IMODE(claim.stat().st_mode)
        assert fmode & 0o077 == 0


def test_label_from_callback_message():
    msg = {
        "reply_markup": {
            "inline_keyboard": [[{"text": "Yes", "callback_data": "yes"}]]
        }
    }
    assert btn.label_from_callback_message(msg, "yes") == "Yes"
    assert btn.label_from_callback_message(msg, "no") is None

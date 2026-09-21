"""Inline keyboard helpers and claim_message_tap (first tap wins)."""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

# Telegram Bot API: callback_data max 1–64 bytes.
CALLBACK_DATA_MAX = 64
_MAP_NAME = "callback_map.json"
_MAP_MAX_ENTRIES = 2000
_CLAIM_NAME = "callback_claimed.json"
_CLAIM_MAX = 500


def normalize_buttons(buttons: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Normalize [{id, label}] (label may also be ``text``)."""
    if not buttons:
        return []
    out: list[dict[str, str]] = []
    for i, row in enumerate(buttons):
        if not isinstance(row, dict):
            raise ValueError(f"buttons[{i}] must be an object")
        bid = str(row.get("id") or "").strip()
        label = str(row.get("label") or row.get("text") or "").strip()
        if not bid or not label:
            raise ValueError(f"buttons[{i}] needs id and label")
        out.append({"id": bid, "label": label})
    return out


def parse_buttons_arg(raw: str) -> list[dict[str, str]]:
    """Parse ``id:Label|id:Label`` into ``[{id, label}, ...]``."""
    text = (raw or "").strip()
    if not text:
        return []
    out: list[dict[str, str]] = []
    for part in text.split("|"):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise ValueError(f"button needs id:Label, got {part!r}")
        bid, label = part.split(":", 1)
        bid = bid.strip()
        label = label.strip()
        if not bid or not label:
            raise ValueError(f"empty id or label in {part!r}")
        out.append({"id": bid, "label": label})
    return out


def _map_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _MAP_NAME


def _load_map(data_dir: Path) -> dict[str, Any]:
    p = _map_path(data_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_map(data_dir: Path, mapping: dict[str, Any]) -> None:
    if len(mapping) > _MAP_MAX_ENTRIES:
        items = sorted(
            mapping.items(),
            key=lambda kv: float((kv[1] or {}).get("ts") or 0),
        )
        mapping = dict(items[-_MAP_MAX_ENTRIES:])
    _map_path(data_dir).write_text(
        json.dumps(mapping, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _callback_data_for(button_id: str, chat_id: int, data_dir: Path | None) -> str:
    """Return callback_data ≤64 bytes; map long ids via short token."""
    raw = (button_id or "").strip()
    encoded = raw.encode("utf-8")
    if 1 <= len(encoded) <= CALLBACK_DATA_MAX and "\n" not in raw:
        return raw
    if data_dir is None:
        raise ValueError(
            f"button id exceeds {CALLBACK_DATA_MAX} bytes; configure data_dir for mapping"
        )
    token = secrets.token_hex(4)
    key = f"{chat_id}:{token}"
    mapping = _load_map(data_dir)
    mapping[key] = {"id": raw, "ts": time.time()}
    _save_map(data_dir, mapping)
    cb = f"t:{token}"
    assert len(cb.encode("utf-8")) <= CALLBACK_DATA_MAX
    return cb


def resolve_callback_data(data_dir: Path, chat_id: int, callback_data: str) -> str:
    """Map callback_data back to the agent-facing button id."""
    raw = (callback_data or "").strip()
    if raw.startswith("t:") and len(raw) > 2:
        token = raw[2:]
        key = f"{chat_id}:{token}"
        mapping = _load_map(data_dir)
        row = mapping.get(key)
        if isinstance(row, dict) and row.get("id"):
            return str(row["id"])
    return raw


def build_inline_keyboard(
    buttons: list[dict[str, str]],
    *,
    chat_id: int,
    data_dir: Path | None = None,
    row_width: int = 2,
) -> dict[str, Any]:
    """Build Telegram InlineKeyboardMarkup from [{id, label}, ...]."""
    if not buttons:
        raise ValueError("buttons list is empty")
    rows: list[list[dict[str, str]]] = []
    row: list[dict[str, str]] = []
    for btn in buttons:
        bid = str(btn.get("id") or "").strip()
        label = str(btn.get("label") or btn.get("text") or "").strip()
        if not bid or not label:
            raise ValueError(f"invalid button: {btn!r}")
        text = label[:64]
        cb = _callback_data_for(bid, chat_id, data_dir)
        row.append({"text": text, "callback_data": cb})
        if len(row) >= max(1, row_width):
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def _claim_path(data_dir: Path) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / _CLAIM_NAME


def claim_message_tap(
    data_dir: Path,
    chat_id: int,
    message_id: int,
    *,
    verb: str,
    uid: int,
) -> bool:
    """First tap on a message wins. Return True if claimed; False if duplicate."""
    path = _claim_path(data_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    key = f"{int(chat_id)}:{int(message_id)}"
    if key in data:
        return False
    data[key] = {"verb": verb, "uid": int(uid), "ts": time.time()}
    if len(data) > _CLAIM_MAX:
        items = sorted(data.items(), key=lambda kv: float((kv[1] or {}).get("ts") or 0))
        data = dict(items[-_CLAIM_MAX:])
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return True


def label_from_callback_message(msg: dict[str, Any], callback_data: str) -> str | None:
    """Best-effort label from the tapped message's inline keyboard."""
    raw = (callback_data or "").strip()
    markup = (msg or {}).get("reply_markup") or {}
    rows = markup.get("inline_keyboard") or []
    for row in rows:
        if not isinstance(row, list):
            continue
        for btn in row:
            if not isinstance(btn, dict):
                continue
            if str(btn.get("callback_data") or "") == raw:
                text = str(btn.get("text") or "").strip()
                return text or None
    return None

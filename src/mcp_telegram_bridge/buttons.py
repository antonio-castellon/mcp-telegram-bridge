"""Inline keyboard helpers and claim_message_tap (first tap wins)."""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any, Iterator
from contextlib import contextmanager

# Telegram Bot API: callback_data max 1-64 bytes.
CALLBACK_DATA_MAX = 64
_MAP_NAME = "callback_map.json"
_MAP_MAX_ENTRIES = 2000
_CLAIM_NAME = "callback_claimed.json"
_CLAIM_MAX = 500
_DIR_MODE = 0o700
_FILE_MODE = 0o600


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


def _ensure_data_dir(data_dir: Path) -> Path:
    """Create data_dir with owner-only permissions when possible."""
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(data_dir, _DIR_MODE)
    except OSError:
        # Windows / non-POSIX FS may ignore or reject mode bits.
        pass
    return data_dir


def _write_text_secure(path: Path, text: str) -> None:
    """Atomically write UTF-8 text and tighten file mode to 0o600 when possible."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(str(tmp), flags, _FILE_MODE)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
    finally:
        if fd >= 0:
            os.close(fd)
    os.replace(str(tmp), str(path))
    try:
        os.chmod(path, _FILE_MODE)
    except OSError:
        pass


@contextmanager
def _file_lock(lock_path: Path) -> Iterator[None]:
    """Cross-platform exclusive lock around claim/map RMW (stdlib only)."""
    _ensure_data_dir(lock_path.parent)
    # Open/create lock file; keep handle for duration of critical section.
    flags = os.O_RDWR | os.O_CREAT
    fd = os.open(str(lock_path), flags, _FILE_MODE)
    try:
        if sys.platform == "win32":
            import msvcrt

            # Lock one byte; retry briefly for contested claims.
            deadline = time.time() + 5.0
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.time() >= deadline:
                        raise
                    time.sleep(0.01)
            try:
                yield
            finally:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _map_path(data_dir: Path) -> Path:
    _ensure_data_dir(data_dir)
    return data_dir / _MAP_NAME


def _load_map(data_dir: Path) -> dict[str, Any]:
    p = _map_path(data_dir)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}


def _save_map(data_dir: Path, mapping: dict[str, Any]) -> None:
    if len(mapping) > _MAP_MAX_ENTRIES:
        items = sorted(
            mapping.items(),
            key=lambda kv: float((kv[1] or {}).get("ts") or 0),
        )
        mapping = dict(items[-_MAP_MAX_ENTRIES:])
    _write_text_secure(
        _map_path(data_dir),
        json.dumps(mapping, ensure_ascii=False, indent=2),
    )


def _callback_data_for(button_id: str, chat_id: int, data_dir: Path | None) -> str:
    """Return callback_data <=64 bytes; map long ids via short token."""
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
    lock = data_dir / ".callback_map.lock"
    with _file_lock(lock):
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
    _ensure_data_dir(data_dir)
    return data_dir / _CLAIM_NAME


def _claim_sentinel_path(data_dir: Path, key: str) -> Path:
    """Per-claim sentinel used for O_EXCL atomic first-wins."""
    safe = key.replace(":", "_").replace("/", "_").replace("\\", "_")
    claims = data_dir / "claims"
    _ensure_data_dir(claims)
    return claims / f"{safe}.claimed"


def claim_message_tap(
    data_dir: Path,
    chat_id: int,
    message_id: int,
    *,
    verb: str,
    uid: int,
) -> bool:
    """First tap on a message wins. Return True if claimed; False if duplicate.

    Atomicity: exclusive create (``O_CREAT|O_EXCL``) of a per-message sentinel
    under ``data_dir/claims/``, plus a process lock around the JSON index update.
    """
    _ensure_data_dir(data_dir)
    key = f"{int(chat_id)}:{int(message_id)}"
    sentinel = _claim_sentinel_path(data_dir, key)
    payload = {"verb": verb, "uid": int(uid), "ts": time.time()}
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    try:
        fd = os.open(str(sentinel), flags, _FILE_MODE)
    except FileExistsError:
        return False
    except OSError:
        # Windows may raise PermissionError / OSError instead of FileExistsError
        # when the exclusive create races; treat existing file as lost race.
        if sentinel.exists():
            return False
        raise
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fd = -1
            fh.write(json.dumps(payload, ensure_ascii=False))
            fh.flush()
    finally:
        if fd >= 0:
            os.close(fd)
    try:
        os.chmod(sentinel, _FILE_MODE)
    except OSError:
        pass

    # Maintain aggregate index for compatibility / pruning (best-effort under lock).
    path = _claim_path(data_dir)
    lock = data_dir / ".callback_claimed.lock"
    with _file_lock(lock):
        try:
            data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        except (OSError, UnicodeError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        data[key] = payload
        if len(data) > _CLAIM_MAX:
            items = sorted(
                data.items(), key=lambda kv: float((kv[1] or {}).get("ts") or 0)
            )
            data = dict(items[-_CLAIM_MAX:])
        _write_text_secure(path, json.dumps(data, ensure_ascii=False, indent=2))
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

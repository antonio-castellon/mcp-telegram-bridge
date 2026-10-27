"""Bounds for polling, update size, rate, and duplicate delivery.

The process does not keep a queue of update bodies between tool calls.
Each ``telegram_get_updates`` call is capped, and in-memory bookkeeping
(rate windows, seen update ids) has a fixed maximum size.
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict, deque
from typing import Any, Callable

UPDATES_LIMIT_MAX = 100
UPDATES_TIMEOUT_MAX = 50
DEDUPE_MAX = 2048
RATE_LIMIT_MAX_KEYS = 1024


def clamp_updates_limit(limit: int | None) -> int | None:
    """Clamp getUpdates ``limit`` to Telegram's 1..100 range."""
    if limit is None:
        return None
    return max(1, min(int(limit), UPDATES_LIMIT_MAX))


def clamp_updates_timeout(timeout: int | None) -> int | None:
    """Clamp getUpdates long-poll ``timeout`` to 0..50 seconds."""
    if timeout is None:
        return None
    return max(0, min(int(timeout), UPDATES_TIMEOUT_MAX))


def iter_inbound_texts(update: dict[str, Any]) -> list[str]:
    """Return user-controlled text fields carried by one update."""
    texts: list[str] = []
    for key in ("message", "edited_message"):
        msg = update.get(key)
        if not isinstance(msg, dict):
            continue
        for field in ("text", "caption"):
            value = msg.get(field)
            if isinstance(value, str):
                texts.append(value)
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        data = callback.get("data")
        if isinstance(data, str):
            texts.append(data)
        msg = callback.get("message")
        if isinstance(msg, dict):
            for field in ("text", "caption"):
                value = msg.get(field)
                if isinstance(value, str):
                    texts.append(value)
    return texts


def withhold_reason(
    update: dict[str, Any],
    *,
    max_chars: int,
    max_bytes: int,
) -> str | None:
    """Return a content-free reason when an update is too large to return."""
    for text in iter_inbound_texts(update):
        if len(text) > max_chars:
            return f"inbound text exceeds {max_chars} characters"
    try:
        encoded = json.dumps(update, ensure_ascii=False, default=str).encode("utf-8")
    except (TypeError, ValueError):
        return "inbound update could not be measured"
    if len(encoded) > max_bytes:
        return f"inbound update exceeds {max_bytes} bytes"
    return None


class SlidingWindowLimiter:
    """Fixed-window counters with a cap on how many keys are remembered.

    A ``None`` rate disables that dimension. Rejected calls are not recorded,
    so a retry succeeds once the window slides forward.
    """

    def __init__(
        self,
        per_key: tuple[int, float] | None,
        global_rate: tuple[int, float] | None,
        *,
        max_keys: int = RATE_LIMIT_MAX_KEYS,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._per_key = per_key
        self._global_rate = global_rate
        self._max_keys = max(1, max_keys)
        self._time = time_fn or time.monotonic
        self._keys: OrderedDict[str, deque[float]] = OrderedDict()
        self._global: deque[float] = deque()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._per_key is not None or self._global_rate is not None

    def _prune(self, hits: deque[float], now: float, window: float) -> None:
        while hits and now - hits[0] >= window:
            hits.popleft()

    def _wait(self, hits: deque[float], now: float, rate: tuple[int, float] | None) -> float:
        if rate is None:
            return 0.0
        count, window = rate
        if count <= 0 or window <= 0:
            return 0.0
        self._prune(hits, now, window)
        if len(hits) < count:
            return 0.0
        return max(0.0, window - (now - hits[0]))

    def retry_after(self, key: str | None = None, *, now: float | None = None) -> float:
        """Seconds until ``allow`` would succeed. Zero if it would succeed now."""
        moment = self._time() if now is None else now
        with self._lock:
            wait = self._wait(self._global, moment, self._global_rate)
            if key is not None and self._per_key is not None:
                hits = self._keys.get(key)
                if hits is not None:
                    wait = max(wait, self._wait(hits, moment, self._per_key))
            return wait

    def allow(self, key: str | None = None, *, now: float | None = None) -> bool:
        """Record one event and return whether it is inside the limits."""
        moment = self._time() if now is None else now
        with self._lock:
            if self._wait(self._global, moment, self._global_rate) > 0:
                return False
            hits: deque[float] | None = None
            if key is not None and self._per_key is not None:
                hits = self._keys.get(key)
                if hits is not None and self._wait(hits, moment, self._per_key) > 0:
                    return False
            if self._global_rate is not None:
                self._global.append(moment)
            if key is not None and self._per_key is not None:
                if hits is None:
                    while len(self._keys) >= self._max_keys:
                        self._keys.popitem(last=False)
                    hits = deque()
                    self._keys[key] = hits
                else:
                    self._keys.move_to_end(key)
                hits.append(moment)
            return True


class UpdateDeduper:
    """Remember update ids whose content was already returned to the host.

    The cache is bounded. Forgetting an old id can show that update again if
    the host re-polls it; it cannot grow without limit.
    """

    def __init__(self, max_size: int = DEDUPE_MAX) -> None:
        self._max = max(1, max_size)
        self._order: deque[int] = deque()
        self._seen: set[int] = set()
        self._lock = threading.Lock()

    def contains(self, update_id: int) -> bool:
        with self._lock:
            return update_id in self._seen

    def remember(self, update_id: int) -> None:
        with self._lock:
            if update_id in self._seen:
                return
            self._seen.add(update_id)
            self._order.append(update_id)
            while len(self._order) > self._max:
                self._seen.discard(self._order.popleft())

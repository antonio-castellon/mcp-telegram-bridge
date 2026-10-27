"""Rate windows, dedupe cache, and update clamps."""

from __future__ import annotations

from mcp_telegram_bridge.limits import (
    SlidingWindowLimiter,
    UpdateDeduper,
    clamp_updates_limit,
    clamp_updates_timeout,
    withhold_reason,
)


def test_clamp_updates_bounds():
    assert clamp_updates_limit(None) is None
    assert clamp_updates_limit(0) == 1
    assert clamp_updates_limit(100) == 100
    assert clamp_updates_limit(10_000) == 100
    assert clamp_updates_timeout(None) is None
    assert clamp_updates_timeout(-5) == 0
    assert clamp_updates_timeout(50) == 50
    assert clamp_updates_timeout(999) == 50


def test_sliding_window_per_key_and_global():
    clock = {"now": 0.0}
    limiter = SlidingWindowLimiter((2, 10.0), (3, 10.0), time_fn=lambda: clock["now"])
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True
    assert limiter.allow("b") is False  # global cap of 3
    clock["now"] = 10.0
    assert limiter.allow("a") is True
    assert limiter.retry_after("a") == 0.0


def test_sliding_window_retry_after_and_disabled():
    clock = {"now": 5.0}
    limiter = SlidingWindowLimiter((1, 10.0), None, time_fn=lambda: clock["now"])
    assert limiter.allow("chat", now=5.0) is True
    assert limiter.allow("chat", now=5.0) is False
    assert limiter.retry_after("chat", now=5.0) == 10.0
    assert limiter.retry_after("chat", now=14.0) == 1.0
    open_limiter = SlidingWindowLimiter(None, None, time_fn=lambda: clock["now"])
    assert open_limiter.allow("x") is True
    assert open_limiter.retry_after("x") == 0.0


def test_key_eviction_does_not_drop_the_global_cap():
    clock = {"now": 0.0}
    limiter = SlidingWindowLimiter((1, 60.0), (2, 60.0), max_keys=1, time_fn=lambda: clock["now"])
    assert limiter.allow("a") is True
    assert limiter.allow("b") is True  # evicts a, global hits 2
    assert limiter.allow("a") is False


def test_deduper_is_bounded():
    deduper = UpdateDeduper(max_size=2)
    deduper.remember(1)
    deduper.remember(2)
    assert deduper.contains(1) is True
    deduper.remember(3)
    assert deduper.contains(1) is False
    assert deduper.contains(3) is True
    deduper.remember(3)
    assert deduper.contains(3) is True


def test_withhold_reason_reports_length_without_echoing_text():
    text = "UNIQUE-PAYLOAD-" + ("x" * 50)
    update = {"update_id": 1, "message": {"text": text, "chat": {"id": 1}}}
    reason = withhold_reason(update, max_chars=20, max_bytes=10_000)
    assert reason is not None
    assert "20" in reason
    assert "UNIQUE-PAYLOAD" not in reason
    assert withhold_reason(update, max_chars=10_000, max_bytes=30) is not None
    assert withhold_reason({"update_id": 1, "message": {"text": "hi"}}, max_chars=10, max_bytes=10_000) is None

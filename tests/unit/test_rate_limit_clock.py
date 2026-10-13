"""Hermetic RPM window clock — minute-boundary flake guard (#1614)."""

from __future__ import annotations

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter, WINDOW_SECONDS


def test_wall_time_hook_keeps_rpm_window_stable_near_boundary(monkeypatch):
    """Two increments near :59.9 share one window when _wall_time is frozen."""
    frozen = float(WINDOW_SECONDS) - 0.1  # 59.9s into the first window
    monkeypatch.setattr("daari.auth.rate_limit._wall_time", lambda: frozen)
    limiter = RateLimiter(MemoryCounterBackend(), default_rpm=1)
    first = limiter.check(key_id="k", model="m", tokens=1)
    second = limiter.check(key_id="k", model="m", tokens=1)
    assert first.allowed is True
    assert second.allowed is False


def test_wall_time_default_is_wall_clock():
    from daari.auth import rate_limit as rl

    before = rl.time.time()
    now = rl._wall_time()
    after = rl.time.time()
    assert before <= now <= after

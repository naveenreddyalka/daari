"""Multi-window budget helpers (issue #174)."""

from __future__ import annotations

from datetime import datetime, timezone

from daari.auth.budgets import (
    merge_windows,
    normalize_duration,
    reset_at,
    window_label,
    windows_from_flat,
)
from daari.auth.virtual_keys import BudgetWindow


def test_normalize_aliases():
    assert normalize_duration("24h") == "day"
    assert normalize_duration("daily") == "day"
    assert normalize_duration("30d") == "month"
    assert normalize_duration("7d") == "7d"


def test_windows_from_flat_skips_unlimited():
    assert windows_from_flat() == ()
    assert windows_from_flat(daily_usd=2, monthly_usd=0) == (BudgetWindow("day", 2.0),)


def test_merge_tighter_wins_and_inherits_team_only():
    merged = merge_windows(
        [BudgetWindow("day", 10)],
        [BudgetWindow("day", 1), BudgetWindow("7d", 5)],
    )
    by_duration = {w.duration: (w.max_usd, scope) for w, scope in merged}
    assert by_duration["day"] == (1.0, "team")
    assert by_duration["7d"] == (5.0, "team")


def test_reset_at_day_is_next_utc_midnight():
    now = datetime(2026, 8, 27, 15, 30, tzinfo=timezone.utc)
    assert reset_at("day", now=now) == "2026-08-28T00:00:00+00:00"
    assert reset_at("month", now=now).startswith("2026-09-01")
    assert window_label("day") == "daily"
    assert window_label("7d") == "7d"

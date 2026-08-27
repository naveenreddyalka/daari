"""Multi-window virtual-key budgets and team inheritance (issue #174)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal

from daari.auth.virtual_keys import BudgetWindow, Team, VirtualKey

Scope = Literal["key", "team"]

_DAY_ALIASES = {"day", "daily", "24h"}
_MONTH_ALIASES = {"month", "monthly", "30d"}
_DURATION = re.compile(r"^(\d+)([hd])$")


def normalize_duration(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in _DAY_ALIASES:
        return "day"
    if value in _MONTH_ALIASES:
        return "month"
    if _DURATION.match(value):
        return value
    raise ValueError(f"unsupported budget duration: {raw!r}")


def window_label(duration: str) -> str:
    """402 `window` field: keep daily/monthly for the migrated flat keys."""
    canonical = normalize_duration(duration)
    if canonical == "day":
        return "daily"
    if canonical == "month":
        return "monthly"
    return canonical


def windows_from_flat(*, daily_usd: float = 0.0, monthly_usd: float = 0.0) -> tuple[BudgetWindow, ...]:
    out: list[BudgetWindow] = []
    if daily_usd > 0:
        out.append(BudgetWindow("day", float(daily_usd)))
    if monthly_usd > 0:
        out.append(BudgetWindow("month", float(monthly_usd)))
    return tuple(out)


def parse_window_flag(raw: str) -> BudgetWindow:
    """CLI `--window 7d=5`."""
    if "=" not in raw:
        raise ValueError(f"window must be duration=max_usd, got {raw!r}")
    duration, amount = raw.split("=", 1)
    return BudgetWindow(normalize_duration(duration), float(amount))


def merge_windows(
    key_windows: Iterable[BudgetWindow],
    team_windows: Iterable[BudgetWindow] = (),
) -> list[tuple[BudgetWindow, Scope]]:
    """Tighter cap wins per canonical duration. Team-only durations are inherited."""
    merged: dict[str, tuple[BudgetWindow, Scope]] = {}
    for window in team_windows:
        duration = normalize_duration(window.duration)
        if window.max_usd <= 0:
            continue
        merged[duration] = (BudgetWindow(duration, float(window.max_usd)), "team")
    for window in key_windows:
        duration = normalize_duration(window.duration)
        if window.max_usd <= 0:
            continue
        incoming = BudgetWindow(duration, float(window.max_usd))
        existing = merged.get(duration)
        if existing is None or incoming.max_usd < existing[0].max_usd:
            merged[duration] = (incoming, "key")
    return list(merged.values())


def reset_at(duration: str, *, now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    canonical = normalize_duration(duration)
    if canonical == "day":
        nxt = (moment + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return nxt.isoformat()
    if canonical == "month":
        if moment.month == 12:
            nxt = moment.replace(year=moment.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            nxt = moment.replace(month=moment.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return nxt.isoformat()
    match = _DURATION.match(canonical)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = timedelta(hours=amount) if unit == "h" else timedelta(days=amount)
        return (moment + delta).isoformat()
    return moment.isoformat()


def ledger_window(duration: str) -> tuple[str, int | None]:
    """Map a duration onto the day-granularity ledger.

    Hourly windows collapse to the current UTC day — the ledger has no hour column.
    """
    canonical = normalize_duration(duration)
    if canonical == "day":
        return "day", None
    if canonical == "month":
        return "month", None
    match = _DURATION.match(canonical)
    if match and match.group(2) == "d":
        return "days", int(match.group(1))
    return "day", None


def budget_error(
    *,
    client_id: str,
    window: BudgetWindow,
    spend: float,
    scope: Scope,
) -> dict[str, Any]:
    label = window_label(window.duration)
    reset = reset_at(window.duration)
    return {
        "type": "budget_exceeded",
        "message": (
            f"Virtual key {label} frontier budget "
            f"(${window.max_usd:.4f}) exceeded — ${spend:.4f} spent. "
            f"Resets at {reset}."
        ),
        "client_id": client_id,
        "window": label,
        "budget_usd": round(window.max_usd, 6),
        "spend_usd": round(spend, 6),
        "reset_at": reset,
        "scope": scope,
    }


def effective_windows(key: VirtualKey, team: Team | None) -> list[tuple[BudgetWindow, Scope]]:
    key_windows = key.budget_windows or windows_from_flat(
        daily_usd=key.daily_budget_usd, monthly_usd=key.monthly_budget_usd
    )
    team_windows = team.budget_windows if team is not None else ()
    return merge_windows(key_windows, team_windows)


def spend_for_window(
    ledger: Any,
    client_ids: list[str],
    duration: str,
    *,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> float:
    kind, days = ledger_window(duration)
    total = 0.0
    for client_id in client_ids:
        if kind == "days" and hasattr(ledger, "frontier_spend_usd_for_client_days"):
            total += float(
                ledger.frontier_spend_usd_for_client_days(
                    client_id,
                    days=days or 1,
                    pricing=pricing,
                    fallback_per_1k=fallback_per_1k,
                )
            )
        else:
            total += float(
                ledger.frontier_spend_usd_for_client(
                    client_id,
                    window="month" if kind == "month" else "day",
                    pricing=pricing,
                    fallback_per_1k=fallback_per_1k,
                )
            )
    return total


def first_exceeded_window(
    key: VirtualKey,
    team: Team | None,
    ledger: Any,
    *,
    client_id: str,
    team_client_ids: list[str],
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> dict[str, Any] | None:
    for window, scope in effective_windows(key, team):
        ids = team_client_ids if scope == "team" else [client_id]
        spend = spend_for_window(
            ledger, ids, window.duration, pricing=pricing, fallback_per_1k=fallback_per_1k
        )
        if spend >= window.max_usd:
            return budget_error(
                client_id=client_id, window=window, spend=spend, scope=scope
            )
    return None

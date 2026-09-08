"""Multi-window virtual-key budgets and team inheritance (issue #174, #344)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
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


def window_header_label(duration: str) -> str:
    """`x-daari-budget-window` value: `1d`, `1mo`, or the raw `7d` / `12h` form."""
    canonical = normalize_duration(duration)
    if canonical == "day":
        return "1d"
    if canonical == "month":
        return "1mo"
    return canonical


def _clone_window(window: BudgetWindow, duration: str) -> BudgetWindow:
    return BudgetWindow(
        duration,
        float(window.max_usd),
        rollover=bool(window.rollover),
        rollover_cap_multiple=float(window.rollover_cap_multiple or 2.0),
    )


def windows_from_flat(*, daily_usd: float = 0.0, monthly_usd: float = 0.0) -> tuple[BudgetWindow, ...]:
    out: list[BudgetWindow] = []
    if daily_usd > 0:
        out.append(BudgetWindow("day", float(daily_usd)))
    if monthly_usd > 0:
        out.append(BudgetWindow("month", float(monthly_usd)))
    return tuple(out)


def parse_window_flag(raw: str) -> BudgetWindow:
    """CLI `--window 7d=5` or `--window 7d=5:rollover`."""
    if "=" not in raw:
        raise ValueError(f"window must be duration=max_usd, got {raw!r}")
    duration, rest = raw.split("=", 1)
    amount_part, _, flag = rest.partition(":")
    rollover = flag.strip().lower() in {"rollover", "roll", "true", "1"}
    return BudgetWindow(
        normalize_duration(duration),
        float(amount_part),
        rollover=rollover,
    )


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
        merged[duration] = (_clone_window(window, duration), "team")
    for window in key_windows:
        duration = normalize_duration(window.duration)
        if window.max_usd <= 0:
            continue
        incoming = _clone_window(window, duration)
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


def reset_epoch(duration: str, *, now: datetime | None = None) -> int:
    """`reset_at` as epoch seconds, for the `x-daari-budget-reset` header."""
    return int(datetime.fromisoformat(reset_at(duration, now=now)).timestamp())


def period_id(duration: str, *, now: datetime | None = None) -> str:
    """Stable id for the *current* spend window (multi-replica rollover key)."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    canonical = normalize_duration(duration)
    if canonical == "day":
        return moment.strftime("%Y-%m-%d")
    if canonical == "month":
        return moment.strftime("%Y-%m")
    match = _DURATION.match(canonical)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            epoch_day = int(moment.timestamp()) // 86400
            bucket = epoch_day // max(1, amount)
            return f"{amount}d:{bucket}"
        epoch_hour = int(moment.timestamp()) // 3600
        bucket = epoch_hour // max(1, amount)
        return f"{amount}h:{bucket}"
    return moment.strftime("%Y-%m-%d")


def previous_period_id(duration: str, *, now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    canonical = normalize_duration(duration)
    if canonical == "day":
        return (moment - timedelta(days=1)).strftime("%Y-%m-%d")
    if canonical == "month":
        if moment.month == 1:
            prior = moment.replace(year=moment.year - 1, month=12, day=1)
        else:
            prior = moment.replace(month=moment.month - 1, day=1)
        return prior.strftime("%Y-%m")
    match = _DURATION.match(canonical)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "d":
            prior = moment - timedelta(days=amount)
        else:
            prior = moment - timedelta(hours=amount)
        return period_id(canonical, now=prior)
    return (moment - timedelta(days=1)).strftime("%Y-%m-%d")


def effective_limit(base_limit: float, *, carry_usd: float, cap_multiple: float) -> float:
    base = float(base_limit)
    if base <= 0:
        return 0.0
    cap = max(1.0, float(cap_multiple or 2.0))
    return min(base + max(0.0, float(carry_usd)), base * cap)


def compute_carry_usd(
    *,
    base_limit: float,
    prev_limit: float,
    prev_spent: float,
    cap_multiple: float,
) -> float:
    """Unused headroom from the prior window, capped so effective ≤ base * multiple."""
    base = float(base_limit)
    if base <= 0:
        return 0.0
    unused = max(0.0, float(prev_limit) - float(prev_spent))
    max_carry = base * (max(1.0, float(cap_multiple or 2.0)) - 1.0)
    return min(unused, max_carry)


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
    limit_usd: float | None = None,
) -> dict[str, Any]:
    label = window_label(window.duration)
    reset = reset_at(window.duration)
    limit = float(window.max_usd if limit_usd is None else limit_usd)
    return {
        "type": "budget_exceeded",
        "message": (
            f"Virtual key {label} frontier budget "
            f"(${limit:.4f}) exceeded — ${spend:.4f} spent. "
            f"Resets at {reset}."
        ),
        "client_id": client_id,
        "window": label,
        "budget_usd": round(limit, 6),
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
    day: str | None = None,
    month: str | None = None,
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
            kwargs: dict[str, Any] = {
                "window": "month" if kind == "month" else "day",
                "pricing": pricing,
                "fallback_per_1k": fallback_per_1k,
            }
            if kind == "month" and month is not None:
                kwargs["month"] = month
            if kind != "month" and day is not None:
                kwargs["day"] = day
            total += float(ledger.frontier_spend_usd_for_client(client_id, **kwargs))
    return total


def _previous_period_spend(
    ledger: Any,
    client_ids: list[str],
    duration: str,
    *,
    prev_period: str,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> float:
    canonical = normalize_duration(duration)
    if canonical == "month":
        return spend_for_window(
            ledger,
            client_ids,
            duration,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
            month=prev_period,
        )
    if canonical == "day":
        return spend_for_window(
            ledger,
            client_ids,
            duration,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
            day=prev_period,
        )
    # Rolling Nd/Nh: approximate prior window as the prior calendar day total.
    return spend_for_window(
        ledger,
        client_ids,
        "day",
        pricing=pricing,
        fallback_per_1k=fallback_per_1k,
        day=previous_period_id("day"),
    )


def resolve_carry_usd(
    window: BudgetWindow,
    *,
    scope: Scope,
    scope_id: str,
    client_ids: list[str],
    ledger: Any,
    now: datetime | None = None,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> float:
    """Carry unused headroom into this period; persist when the ledger supports it."""
    if not window.rollover:
        return 0.0
    moment = now or datetime.now(timezone.utc)
    duration = normalize_duration(window.duration)
    current = period_id(duration, now=moment)
    getter = getattr(ledger, "get_budget_window_state", None)
    putter = getattr(ledger, "put_budget_window_state", None)
    row = getter(scope, scope_id, duration) if callable(getter) else None
    if isinstance(row, dict) and row.get("period_id") == current:
        return max(0.0, float(row.get("carry_usd") or 0.0))

    old_carry = 0.0
    prev = previous_period_id(duration, now=moment)
    if isinstance(row, dict) and row.get("period_id") == prev:
        old_carry = max(0.0, float(row.get("carry_usd") or 0.0))
    base = float(window.max_usd)
    cap = float(window.rollover_cap_multiple or 2.0)
    prev_limit = effective_limit(base, carry_usd=old_carry, cap_multiple=cap)
    prev_spent = _previous_period_spend(
        ledger,
        client_ids,
        duration,
        prev_period=prev,
        pricing=pricing,
        fallback_per_1k=fallback_per_1k,
    )
    carry = compute_carry_usd(
        base_limit=base,
        prev_limit=prev_limit,
        prev_spent=prev_spent,
        cap_multiple=cap,
    )
    if callable(putter):
        putter(scope, scope_id, duration, period_id=current, carry_usd=carry)
    return carry


@dataclass(frozen=True)
class WindowStatus:
    """One effective budget window measured against current spend (#319, #344)."""

    window: BudgetWindow
    scope: Scope
    spend: float
    carry_usd: float = 0.0
    now: datetime | None = field(default=None, compare=False)

    @property
    def limit(self) -> float:
        return effective_limit(
            float(self.window.max_usd),
            carry_usd=self.carry_usd if self.window.rollover else 0.0,
            cap_multiple=float(self.window.rollover_cap_multiple or 2.0),
        )

    @property
    def remaining(self) -> float:
        return max(0.0, self.limit - float(self.spend))

    @property
    def exceeded(self) -> bool:
        return float(self.spend) >= self.limit

    @property
    def reset_at(self) -> str:
        return reset_at(self.window.duration, now=self.now)

    @property
    def reset_epoch(self) -> int:
        return reset_epoch(self.window.duration, now=self.now)


def budget_status(
    key: VirtualKey,
    team: Team | None,
    ledger: Any,
    *,
    client_id: str,
    team_client_ids: list[str],
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
    now: datetime | None = None,
) -> list[WindowStatus]:
    """Spend vs cap for every effective window, in `effective_windows` order."""
    statuses: list[WindowStatus] = []
    for window, scope in effective_windows(key, team):
        ids = team_client_ids if scope == "team" else [client_id]
        spend = spend_for_window(
            ledger, ids, window.duration, pricing=pricing, fallback_per_1k=fallback_per_1k
        )
        scope_id = client_id if scope == "key" else (team.team_id if team is not None else client_id)
        carry = resolve_carry_usd(
            window,
            scope=scope,
            scope_id=scope_id,
            client_ids=ids,
            ledger=ledger,
            now=now,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        statuses.append(
            WindowStatus(window=window, scope=scope, spend=spend, carry_usd=carry, now=now)
        )
    return statuses


def tightest_window(statuses: Iterable[WindowStatus]) -> WindowStatus | None:
    """The window a client will hit first: least USD remaining (first wins ties)."""
    best: WindowStatus | None = None
    for status in statuses:
        if best is None or status.remaining < best.remaining:
            best = status
    return best


def first_exceeded_window(
    key: VirtualKey,
    team: Team | None,
    ledger: Any,
    *,
    client_id: str,
    team_client_ids: list[str],
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    statuses = budget_status(
        key,
        team,
        ledger,
        client_id=client_id,
        team_client_ids=team_client_ids,
        pricing=pricing,
        fallback_per_1k=fallback_per_1k,
        now=now,
    )
    exceeded = next((status for status in statuses if status.exceeded), None)
    if exceeded is None:
        return None
    return budget_error(
        client_id=client_id,
        window=exceeded.window,
        spend=exceeded.spend,
        scope=exceeded.scope,
        limit_usd=exceeded.limit,
    )

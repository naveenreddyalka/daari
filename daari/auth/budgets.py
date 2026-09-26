"""Multi-window virtual-key budgets and team inheritance (issue #174, #344)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Literal

from daari.auth.virtual_keys import BudgetWindow, Team, VirtualKey

Scope = Literal["key", "team", "user", "model_group"]

_DAY_ALIASES = {"day", "daily", "24h"}
_MONTH_ALIASES = {"month", "monthly", "30d"}
_WEEK_ALIASES = {"week", "weekly", "rpw", "1w"}
_LIFETIME_ALIASES = {"lifetime", "total", "all", "alltime", "all-time"}
_DURATION = re.compile(r"^(\d+)([hd])$")


def normalize_duration(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in _DAY_ALIASES:
        return "day"
    if value in _WEEK_ALIASES:
        return "week"
    if value in _MONTH_ALIASES:
        return "month"
    if value in _LIFETIME_ALIASES:
        return "lifetime"
    if _DURATION.match(value):
        return value
    raise ValueError(f"unsupported budget duration: {raw!r}")


def window_label(duration: str) -> str:
    """402 `window` field: keep daily/monthly for the migrated flat keys."""
    canonical = normalize_duration(duration)
    if canonical == "day":
        return "daily"
    if canonical == "week":
        return "weekly"
    if canonical == "month":
        return "monthly"
    if canonical == "lifetime":
        return "lifetime"
    return canonical


def window_header_label(duration: str) -> str:
    """`x-daari-budget-window` value: `1d`, `1w`, `1mo`, or the raw `7d` / `12h` form."""
    canonical = normalize_duration(duration)
    if canonical == "day":
        return "1d"
    if canonical == "week":
        return "1w"
    if canonical == "month":
        return "1mo"
    if canonical == "lifetime":
        return "lifetime"
    return canonical


def _clone_window(window: BudgetWindow, duration: str) -> BudgetWindow:
    rollover = bool(window.rollover) and duration != "lifetime"
    return BudgetWindow(
        duration,
        float(window.max_usd),
        rollover=rollover,
        rollover_cap_multiple=float(window.rollover_cap_multiple or 2.0),
        max_requests=int(window.max_requests or 0),
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
    canonical = normalize_duration(duration)
    # Lifetime caps never roll — there is no next period (#936).
    rollover = (
        canonical != "lifetime"
        and flag.strip().lower() in {"rollover", "roll", "true", "1"}
    )
    return BudgetWindow(
        canonical,
        float(amount_part),
        rollover=rollover,
    )


def parse_window_requests_flag(raw: str) -> BudgetWindow:
    """CLI `--window-requests 1d=5000` — request-count cap, no USD (#467)."""
    if "=" not in raw:
        raise ValueError(f"window-requests must be duration=max_requests, got {raw!r}")
    duration, amount_part = raw.split("=", 1)
    amount_part = amount_part.split(":", 1)[0].strip()
    try:
        max_requests = int(amount_part)
    except ValueError as exc:
        raise ValueError(f"window-requests count must be an integer, got {raw!r}") from exc
    if max_requests <= 0:
        raise ValueError(f"window-requests count must be > 0, got {raw!r}")
    return BudgetWindow(
        normalize_duration(duration),
        0.0,
        max_requests=max_requests,
    )


def coalesce_windows(windows: Iterable[BudgetWindow]) -> tuple[BudgetWindow, ...]:
    """Combine same-duration windows so USD and request caps share one entry."""
    merged: dict[str, BudgetWindow] = {}
    for window in windows:
        duration = normalize_duration(window.duration)
        max_usd = float(window.max_usd or 0.0)
        max_requests = int(window.max_requests or 0)
        if max_usd <= 0 and max_requests <= 0:
            continue
        existing = merged.get(duration)
        if existing is None:
            merged[duration] = _clone_window(window, duration)
            continue
        # Prefer explicitly set dimensions; if both set, keep the tighter.
        usd = existing.max_usd
        if max_usd > 0:
            usd = max_usd if usd <= 0 else min(usd, max_usd)
        reqs = existing.max_requests
        if max_requests > 0:
            reqs = max_requests if reqs <= 0 else min(reqs, max_requests)
        rollover = bool(existing.rollover or window.rollover)
        cap = float(existing.rollover_cap_multiple or window.rollover_cap_multiple or 2.0)
        merged[duration] = BudgetWindow(
            duration,
            float(usd),
            rollover=rollover,
            rollover_cap_multiple=cap,
            max_requests=int(reqs),
        )
    return tuple(merged.values())


def merge_windows(
    key_windows: Iterable[BudgetWindow],
    team_windows: Iterable[BudgetWindow] = (),
) -> list[tuple[BudgetWindow, Scope]]:
    """Tighter cap wins per canonical duration. Team-only durations are inherited.

    USD and request-count dimensions merge independently (#467). When both are
    present on one duration, ``scope`` follows the USD winner (request scope is
    recovered in ``budget_status`` via ``merge_window_scopes``).
    """
    return [
        (item.window, item.usd_scope or item.request_scope or "key")
        for item in merge_window_scopes(key_windows, team_windows)
    ]


@dataclass(frozen=True)
class MergedCaps:
    """Effective caps for one duration after key/team merge (#467)."""

    window: BudgetWindow
    usd_scope: Scope | None = None
    request_scope: Scope | None = None


def merge_window_scopes(
    key_windows: Iterable[BudgetWindow],
    team_windows: Iterable[BudgetWindow] = (),
) -> list[MergedCaps]:
    usd_by: dict[str, tuple[float, Scope, BudgetWindow]] = {}
    req_by: dict[str, tuple[int, Scope]] = {}

    def _ingest(windows: Iterable[BudgetWindow], scope: Scope) -> None:
        for window in windows:
            duration = normalize_duration(window.duration)
            if float(window.max_usd or 0) > 0:
                amount = float(window.max_usd)
                existing = usd_by.get(duration)
                if existing is None or amount < existing[0]:
                    usd_by[duration] = (amount, scope, window)
            if int(window.max_requests or 0) > 0:
                count = int(window.max_requests)
                existing_r = req_by.get(duration)
                if existing_r is None or count < existing_r[0]:
                    req_by[duration] = (count, scope)

    _ingest(team_windows, "team")
    _ingest(key_windows, "key")

    out: list[MergedCaps] = []
    for duration in set(usd_by) | set(req_by):
        usd_entry = usd_by.get(duration)
        req_entry = req_by.get(duration)
        max_usd = usd_entry[0] if usd_entry else 0.0
        max_requests = req_entry[0] if req_entry else 0
        template = usd_entry[2] if usd_entry else BudgetWindow(duration, 0.0)
        out.append(
            MergedCaps(
                window=BudgetWindow(
                    duration,
                    float(max_usd),
                    rollover=bool(template.rollover) if usd_entry else False,
                    rollover_cap_multiple=float(template.rollover_cap_multiple or 2.0),
                    max_requests=int(max_requests),
                ),
                usd_scope=usd_entry[1] if usd_entry else None,
                request_scope=req_entry[1] if req_entry else None,
            )
        )
    return out


def reset_at(duration: str, *, now: datetime | None = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    canonical = normalize_duration(duration)
    if canonical == "lifetime":
        return ""
    if canonical == "day":
        nxt = (moment + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return nxt.isoformat()
    if canonical == "week":
        # Next Monday 00:00 UTC (ISO week boundary).
        days = (8 - moment.isoweekday()) % 7 or 7
        nxt = (moment + timedelta(days=days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
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
    raw = reset_at(duration, now=now)
    if not raw:
        return 0
    return int(datetime.fromisoformat(raw).timestamp())


def period_id(duration: str, *, now: datetime | None = None) -> str:
    """Stable id for the *current* spend window (multi-replica rollover key)."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    canonical = normalize_duration(duration)
    if canonical == "lifetime":
        return "lifetime"
    if canonical == "day":
        return moment.strftime("%Y-%m-%d")
    if canonical == "week":
        return moment.strftime("%G-W%V")
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
    if canonical == "week":
        weekday = moment.isoweekday()
        monday = (moment - timedelta(days=weekday - 1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        prior = monday - timedelta(days=7)
        return prior.strftime("%G-W%V")
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
    Lifetime sums every day row for the client (#936).
    """
    canonical = normalize_duration(duration)
    if canonical == "lifetime":
        return "lifetime", None
    if canonical == "day":
        return "day", None
    if canonical == "week":
        # Calendar week period ids; spend uses a 7-day ledger rollup (#1067).
        return "days", 7
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
    user_id: str | None = None,
    quota: Literal["usd", "requests"] = "usd",
    spend_requests: int | None = None,
    limit_requests: int | None = None,
    model_group: str | None = None,
) -> dict[str, Any]:
    label = window_label(window.duration)
    reset = reset_at(window.duration)
    lifetime = normalize_duration(window.duration) == "lifetime"
    if quota == "requests":
        limit_r = int(window.max_requests if limit_requests is None else limit_requests)
        used = int(spend if spend_requests is None else spend_requests)
        if lifetime:
            message = (
                f"Virtual key {label} request quota "
                f"({limit_r}) exceeded — {used} used."
            )
        else:
            message = (
                f"Virtual key {label} request quota "
                f"({limit_r}) exceeded — {used} used. "
                f"Resets at {reset}."
            )
        payload: dict[str, Any] = {
            "type": "budget_exceeded",
            "message": message,
            "client_id": client_id,
            "window": label,
            "quota": "requests",
            "budget_requests": limit_r,
            "spend_requests": used,
            "reset_at": reset,
            "scope": scope,
        }
    else:
        limit = float(window.max_usd if limit_usd is None else limit_usd)
        if lifetime:
            message = (
                f"Virtual key {label} frontier budget "
                f"(${limit:.4f}) exceeded — ${spend:.4f} spent."
            )
        else:
            message = (
                f"Virtual key {label} frontier budget "
                f"(${limit:.4f}) exceeded — ${spend:.4f} spent. "
                f"Resets at {reset}."
            )
        payload = {
            "type": "budget_exceeded",
            "message": message,
            "client_id": client_id,
            "window": label,
            "budget_usd": round(limit, 6),
            "spend_usd": round(spend, 6),
            "reset_at": reset,
            "scope": scope,
        }
    if user_id is not None:
        payload["user_id"] = user_id
    if model_group is not None:
        payload["model_group"] = model_group
    return payload


def user_cap_error(
    *,
    client_id: str,
    user_id: str,
    spend: float,
    cap_usd: float,
) -> dict[str, Any]:
    """402 body for a per-end-user daily cap on a shared virtual key (#410)."""
    from daari.auth.virtual_keys import BudgetWindow

    return budget_error(
        client_id=client_id,
        window=BudgetWindow("day", float(cap_usd)),
        spend=spend,
        scope="user",
        limit_usd=float(cap_usd),
        user_id=user_id,
    )


def user_daily_cap_exceeded(
    key: VirtualKey,
    ledger: Any,
    *,
    client_id: str,
    user_id: str | None,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> dict[str, Any] | None:
    """Return a 402 body when this named user is over the key's daily/lifetime user cap.

    Requests without a `user` are never capped (attributed to ``unknown`` only).
    Lifetime user caps live in ``metadata.user_lifetime_usd_cap`` (#936).
    """
    named = (user_id or "").strip()
    if not named:
        return None
    spend_fn = getattr(ledger, "frontier_spend_usd_for_user", None)
    if spend_fn is None:
        return None

    lifetime_cap = float((key.metadata or {}).get("user_lifetime_usd_cap") or 0.0)
    if lifetime_cap > 0:
        spend = float(
            spend_fn(
                client_id,
                named,
                window="lifetime",
                pricing=pricing,
                fallback_per_1k=fallback_per_1k,
            )
            or 0.0
        )
        if spend >= lifetime_cap:
            return budget_error(
                client_id=client_id,
                window=BudgetWindow("lifetime", float(lifetime_cap)),
                spend=spend,
                scope="user",
                limit_usd=float(lifetime_cap),
                user_id=named,
            )

    cap = float(getattr(key, "user_daily_usd_cap", 0.0) or 0.0)
    if cap <= 0:
        return None
    spend = float(
        spend_fn(
            client_id,
            named,
            window="day",
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        or 0.0
    )
    if spend < cap:
        return None
    return user_cap_error(client_id=client_id, user_id=named, spend=spend, cap_usd=cap)


def effective_windows(key: VirtualKey, team: Team | None) -> list[tuple[BudgetWindow, Scope]]:
    key_windows = key.budget_windows or windows_from_flat(
        daily_usd=key.daily_budget_usd, monthly_usd=key.monthly_budget_usd
    )
    team_windows = team.budget_windows if team is not None else ()
    return merge_windows(key_windows, team_windows)


def effective_caps(key: VirtualKey, team: Team | None) -> list[MergedCaps]:
    key_windows = key.budget_windows or windows_from_flat(
        daily_usd=key.daily_budget_usd, monthly_usd=key.monthly_budget_usd
    )
    team_windows = team.budget_windows if team is not None else ()
    return merge_window_scopes(key_windows, team_windows)


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
        if kind == "lifetime":
            if hasattr(ledger, "frontier_spend_usd_for_client"):
                total += float(
                    ledger.frontier_spend_usd_for_client(
                        client_id,
                        window="lifetime",
                        pricing=pricing,
                        fallback_per_1k=fallback_per_1k,
                    )
                )
            continue
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


def requests_for_window(
    ledger: Any,
    client_ids: list[str],
    duration: str,
    *,
    day: str | None = None,
    month: str | None = None,
) -> int:
    """Billable request count (excludes cache hits) across client ids (#467)."""
    kind, days = ledger_window(duration)
    total = 0
    for client_id in client_ids:
        if kind == "lifetime" and hasattr(ledger, "request_count_for_client"):
            total += int(ledger.request_count_for_client(client_id, window="lifetime") or 0)
            continue
        if kind == "days" and hasattr(ledger, "request_count_for_client_days"):
            total += int(
                ledger.request_count_for_client_days(client_id, days=days or 1) or 0
            )
        elif hasattr(ledger, "request_count_for_client"):
            kwargs: dict[str, Any] = {
                "window": "month" if kind == "month" else "day",
            }
            if kind == "month" and month is not None:
                kwargs["month"] = month
            if kind != "month" and day is not None:
                kwargs["day"] = day
            total += int(ledger.request_count_for_client(client_id, **kwargs) or 0)
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
    if not window.rollover or normalize_duration(window.duration) == "lifetime":
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


def _parse_until(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def active_budget_boosts(
    metadata: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return non-expired temporary budget increases (#936)."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    raw = (metadata or {}).get("budget_boosts") or []
    if not isinstance(raw, list):
        return []
    active: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        until = _parse_until(item.get("until"))
        if until is None or until <= moment:
            continue
        usd = float(item.get("usd") or 0.0)
        requests = int(item.get("requests") or 0)
        if usd <= 0 and requests <= 0:
            continue
        active.append(dict(item))
    return active


def expired_budget_boosts(
    metadata: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    raw = (metadata or {}).get("budget_boosts") or []
    if not isinstance(raw, list):
        return []
    expired: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        until = _parse_until(item.get("until"))
        if until is not None and until <= moment:
            expired.append(dict(item))
    return expired


def apply_boost_usd(
    metadata: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> float:
    return sum(float(item.get("usd") or 0.0) for item in active_budget_boosts(metadata, now=now))


def apply_boost_requests(
    metadata: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> int:
    return sum(int(item.get("requests") or 0) for item in active_budget_boosts(metadata, now=now))


def prune_expired_boosts(
    metadata: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop expired boosts from metadata; return (new_meta, expired_rows)."""
    meta = dict(metadata or {})
    expired = expired_budget_boosts(meta, now=now)
    if not expired:
        return meta, []
    expired_ids = {str(item.get("id") or "") for item in expired}
    kept = [
        item
        for item in (meta.get("budget_boosts") or [])
        if isinstance(item, dict) and str(item.get("id") or "") not in expired_ids
    ]
    if kept:
        meta["budget_boosts"] = kept
    else:
        meta.pop("budget_boosts", None)
    return meta, expired


def make_budget_boost(
    *,
    usd: float = 0.0,
    requests: int = 0,
    until: str,
    granted_at: str | None = None,
) -> dict[str, Any]:
    import secrets

    until_dt = _parse_until(until)
    if until_dt is None:
        raise ValueError(f"invalid --until timestamp: {until!r}")
    if float(usd) <= 0 and int(requests) <= 0:
        raise ValueError("budget boost requires --usd and/or --requests > 0")
    granted = granted_at or datetime.now(timezone.utc).isoformat()
    return {
        "id": secrets.token_hex(6),
        "usd": float(usd) if float(usd) > 0 else 0.0,
        "requests": int(requests) if int(requests) > 0 else 0,
        "until": until_dt.isoformat(),
        "granted_at": granted,
    }


@dataclass(frozen=True)
class WindowStatus:
    """One effective budget window measured against current spend (#319, #344, #467)."""

    window: BudgetWindow
    scope: Scope
    spend: float
    carry_usd: float = 0.0
    now: datetime | None = field(default=None, compare=False)
    quota: Literal["usd", "requests"] = "usd"
    boost_usd: float = 0.0
    boost_requests: int = 0
    model_group: str | None = None

    @property
    def limit(self) -> float:
        if self.quota == "requests":
            return float(int(self.window.max_requests or 0) + int(self.boost_requests or 0))
        return effective_limit(
            float(self.window.max_usd),
            carry_usd=self.carry_usd if self.window.rollover else 0.0,
            cap_multiple=float(self.window.rollover_cap_multiple or 2.0),
        ) + max(0.0, float(self.boost_usd or 0.0))

    @property
    def remaining(self) -> float:
        return max(0.0, self.limit - float(self.spend))

    @property
    def exceeded(self) -> bool:
        if self.quota == "requests":
            return int(self.spend) >= int(self.limit)
        return float(self.spend) >= self.limit

    @property
    def ratio(self) -> float:
        cap = float(self.limit)
        if cap <= 0:
            return 0.0
        return float(self.spend) / cap

    def in_soft_band(self, soft_ratio: float) -> bool:
        """True when spend crossed the soft line but not the hard cap (#498)."""
        mark = float(soft_ratio)
        if mark <= 0 or mark > 1.0 or self.exceeded:
            return False
        return self.ratio >= mark

    @property
    def reset_at(self) -> str:
        return reset_at(self.window.duration, now=self.now)

    @property
    def reset_epoch(self) -> int:
        return reset_epoch(self.window.duration, now=self.now)


def _boost_for_scope(
    key: VirtualKey,
    team: Team | None,
    scope: Scope,
    *,
    now: datetime | None = None,
) -> tuple[float, int]:
    if scope == "team" and team is not None:
        meta = getattr(team, "metadata", None) or {}
        # Teams store boosts on the team row via budget_boosts in metadata when present;
        # fall back to empty. Team dataclass has no metadata today — boosts live on
        # store-side team metadata JSON when granted via CLI.
        return apply_boost_usd(meta, now=now), apply_boost_requests(meta, now=now)
    return (
        apply_boost_usd(key.metadata, now=now),
        apply_boost_requests(key.metadata, now=now),
    )


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
    """Spend vs cap for every effective window, in `effective_caps` order.

    A duration with both USD and request caps yields two statuses (#467).
    """
    statuses: list[WindowStatus] = []
    for caps in effective_caps(key, team):
        window = caps.window
        if caps.usd_scope is not None and float(window.max_usd or 0) > 0:
            ids = team_client_ids if caps.usd_scope == "team" else [client_id]
            spend = spend_for_window(
                ledger, ids, window.duration, pricing=pricing, fallback_per_1k=fallback_per_1k
            )
            scope_id = (
                client_id if caps.usd_scope == "key" else (team.team_id if team is not None else client_id)
            )
            carry = resolve_carry_usd(
                window,
                scope=caps.usd_scope,
                scope_id=scope_id,
                client_ids=ids,
                ledger=ledger,
                now=now,
                pricing=pricing,
                fallback_per_1k=fallback_per_1k,
            )
            boost_usd, _ = _boost_for_scope(key, team, caps.usd_scope, now=now)
            statuses.append(
                WindowStatus(
                    window=window,
                    scope=caps.usd_scope,
                    spend=spend,
                    carry_usd=carry,
                    now=now,
                    quota="usd",
                    boost_usd=boost_usd,
                )
            )
        if caps.request_scope is not None and int(window.max_requests or 0) > 0:
            ids = team_client_ids if caps.request_scope == "team" else [client_id]
            used = requests_for_window(ledger, ids, window.duration)
            _, boost_req = _boost_for_scope(key, team, caps.request_scope, now=now)
            statuses.append(
                WindowStatus(
                    window=window,
                    scope=caps.request_scope,
                    spend=float(used),
                    now=now,
                    quota="requests",
                    boost_requests=boost_req,
                )
            )
    return statuses


def tightest_window(statuses: Iterable[WindowStatus]) -> WindowStatus | None:
    """The window a client will hit first: least remaining (first wins ties).

    Prefer USD windows when comparing mixed quotas so existing clients keep
    seeing ``x-daari-budget-*`` for spend; request headers are attached
    separately via ``tightest_request_window``.
    """
    usd = [status for status in statuses if status.quota == "usd"]
    pool = usd or list(statuses)
    best: WindowStatus | None = None
    for status in pool:
        if best is None or status.remaining < best.remaining:
            best = status
    return best


def tightest_request_window(statuses: Iterable[WindowStatus]) -> WindowStatus | None:
    best: WindowStatus | None = None
    for status in statuses:
        if status.quota != "requests":
            continue
        if best is None or status.remaining < best.remaining:
            best = status
    return best


def request_quota_report_rows(
    store: Any,
    ledger: Any,
    *,
    soft_ratio: float,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> list[dict[str, Any]]:
    """Per-key request-quota used/cap/soft for report + FinOps (#519)."""
    rows: list[dict[str, Any]] = []
    if store is None or not getattr(ledger, "enabled", False):
        return rows
    try:
        keys = store.list()
    except Exception:
        return rows
    for key in keys:
        try:
            team = store.get_team(key.team_id) if key.team_id else None
            client_id = key.client_id or key.key_id
            team_ids = store.team_client_ids(team.team_id) if team is not None else []
            statuses = budget_status(
                key,
                team,
                ledger,
                client_id=client_id,
                team_client_ids=team_ids,
                pricing=pricing,
                fallback_per_1k=fallback_per_1k,
            )
        except Exception:
            continue
        for status in statuses:
            if status.quota != "requests":
                continue
            soft = status.in_soft_band(soft_ratio)
            rows.append(
                {
                    "key_id": key.key_id,
                    "name": key.name,
                    "scope": status.scope,
                    "window": window_header_label(status.window.duration),
                    "used": int(status.spend),
                    "cap": int(status.limit),
                    "remaining": int(status.remaining),
                    "soft": soft,
                }
            )
    return rows


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
    if exceeded.quota == "requests":
        return budget_error(
            client_id=client_id,
            window=exceeded.window,
            spend=exceeded.spend,
            scope=exceeded.scope,
            quota="requests",
            spend_requests=int(exceeded.spend),
            limit_requests=int(exceeded.limit),
        )
    return budget_error(
        client_id=client_id,
        window=exceeded.window,
        spend=exceeded.spend,
        scope=exceeded.scope,
        limit_usd=exceeded.limit,
    )


def collect_team_budget_gauges(
    store: Any,
    ledger: Any,
    *,
    fallback_per_1k: float = 0.002,
    pricing: Any = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Snapshot team USD window remaining/limit for Prometheus (#616)."""
    if store is None or not getattr(store, "enabled", False):
        return []
    list_teams = getattr(store, "list_teams", None)
    if not callable(list_teams):
        return []
    if ledger is None or not getattr(ledger, "enabled", False):
        return []
    moment = now or datetime.now(timezone.utc)
    epoch_now = int(moment.timestamp())
    rows: list[dict[str, Any]] = []
    for team in list_teams():
        windows = getattr(team, "budget_windows", ()) or ()
        usd_windows = [w for w in windows if float(getattr(w, "max_usd", 0) or 0) > 0]
        if not usd_windows:
            continue
        client_ids = store.team_client_ids(team.team_id)
        for window in usd_windows:
            spend = spend_for_window(
                ledger,
                client_ids,
                window.duration,
                pricing=pricing,
                fallback_per_1k=fallback_per_1k,
            )
            limit = float(window.max_usd)
            remaining = max(0.0, limit - float(spend))
            hours = max(0.0, (reset_epoch(window.duration, now=moment) - epoch_now) / 3600.0)
            rows.append(
                {
                    "team": team.name,
                    "window": window_label(window.duration),
                    "remaining_usd": round(remaining, 6),
                    "limit_usd": round(limit, 6),
                    "remaining_hours": round(hours, 4),
                }
            )
    return rows


def parse_model_group_budgets(
    raw: Any,
) -> dict[str, tuple[BudgetWindow, ...]]:
    """Parse ``{group: [BudgetWindow|dict, ...]}`` from metadata or create kwargs (#1109)."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, tuple[BudgetWindow, ...]] = {}
    for name, windows in raw.items():
        group = str(name).strip()
        if not group:
            continue
        parsed: list[BudgetWindow] = []
        if not isinstance(windows, (list, tuple)):
            continue
        for item in windows:
            if isinstance(item, BudgetWindow):
                if float(item.max_usd or 0) > 0:
                    parsed.append(
                        BudgetWindow(
                            normalize_duration(item.duration),
                            float(item.max_usd),
                            rollover=bool(item.rollover),
                            rollover_cap_multiple=float(item.rollover_cap_multiple or 2.0),
                        )
                    )
                continue
            if not isinstance(item, dict):
                continue
            max_usd = float(item.get("max_usd") or 0.0)
            if max_usd <= 0:
                continue
            duration = normalize_duration(str(item.get("duration") or "day"))
            parsed.append(
                BudgetWindow(
                    duration,
                    max_usd,
                    rollover=bool(item.get("rollover")),
                    rollover_cap_multiple=float(item.get("rollover_cap_multiple") or 2.0),
                )
            )
        if parsed:
            out[group] = coalesce_windows(parsed)
    return out


def encode_model_group_budgets(
    budgets: dict[str, tuple[BudgetWindow, ...] | list[BudgetWindow]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        name: [w.as_dict() for w in windows]
        for name, windows in budgets.items()
        if windows
    }


def model_group_budgets_of(entity: VirtualKey | Team | None) -> dict[str, tuple[BudgetWindow, ...]]:
    if entity is None:
        return {}
    direct = getattr(entity, "model_group_budgets", None)
    if isinstance(direct, dict) and direct:
        return parse_model_group_budgets(direct)
    meta = getattr(entity, "metadata", None) or {}
    if isinstance(meta, dict):
        return parse_model_group_budgets(meta.get("model_group_budgets"))
    return {}


def merge_model_group_budgets(
    key: VirtualKey,
    team: Team | None,
) -> list[tuple[str, BudgetWindow, Scope]]:
    """Tighter USD window wins per (group, duration); team ingested before key (#1109)."""
    merged: dict[tuple[str, str], tuple[BudgetWindow, Scope]] = {}

    def _ingest(budgets: dict[str, tuple[BudgetWindow, ...]], scope: Scope) -> None:
        for group, windows in budgets.items():
            for window in windows:
                duration = normalize_duration(window.duration)
                amount = float(window.max_usd or 0)
                if amount <= 0:
                    continue
                slot = (group, duration)
                existing = merged.get(slot)
                if existing is None or amount < float(existing[0].max_usd):
                    merged[slot] = (_clone_window(window, duration), scope)

    _ingest(model_group_budgets_of(team), "model_group")
    _ingest(model_group_budgets_of(key), "model_group")
    return [(group, window, scope) for (group, _), (window, scope) in sorted(merged.items())]


def _group_patterns(
    group_name: str,
    catalog: dict[str, list[str]] | None,
) -> list[str]:
    members = (catalog or {}).get(group_name) or []
    if isinstance(members, str):
        members = [members]
    return [str(item).strip() for item in members if str(item).strip()]


def spend_for_model_group_window(
    ledger: Any,
    group_name: str,
    catalog: dict[str, list[str]] | None,
    duration: str,
    *,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> float:
    """Org-wide L6 spend for models matching a named group (#1109)."""
    patterns = _group_patterns(group_name, catalog)
    if not patterns or not hasattr(ledger, "frontier_spend_usd_for_model_patterns"):
        return 0.0
    kind, days = ledger_window(duration)
    if kind == "lifetime":
        return float(
            ledger.frontier_spend_usd_for_model_patterns(
                patterns,
                window="lifetime",
                pricing=pricing,
                fallback_per_1k=fallback_per_1k,
            )
            or 0.0
        )
    if kind == "days":
        return float(
            ledger.frontier_spend_usd_for_model_patterns(
                patterns,
                window="days",
                days=days or 1,
                pricing=pricing,
                fallback_per_1k=fallback_per_1k,
            )
            or 0.0
        )
    return float(
        ledger.frontier_spend_usd_for_model_patterns(
            patterns,
            window="month" if kind == "month" else "day",
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        or 0.0
    )


def model_group_budget_status(
    model: str,
    key: VirtualKey,
    team: Team | None,
    ledger: Any,
    *,
    catalog: dict[str, list[str]] | None,
    client_id: str,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
    now: datetime | None = None,
) -> list[WindowStatus]:
    """Statuses for groups that both match ``model`` and have an attached budget (#1109)."""
    from daari.auth.model_access import groups_for_model

    attached = merge_model_group_budgets(key, team)
    if not attached:
        return []
    matched = set(groups_for_model(model, catalog))
    statuses: list[WindowStatus] = []
    for group_name, window, scope in attached:
        if group_name not in matched:
            continue
        spend = spend_for_model_group_window(
            ledger,
            group_name,
            catalog,
            window.duration,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        statuses.append(
            WindowStatus(
                window=window,
                scope=scope,
                spend=spend,
                now=now,
                quota="usd",
                model_group=group_name,
            )
        )
    return statuses


def model_group_spend_report_rows(
    store: Any,
    ledger: Any,
    *,
    catalog: dict[str, list[str]] | None,
    soft_ratio: float,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> list[dict[str, Any]]:
    """Per-model_group USD totals for report / FinOps (#1109)."""
    rows: list[dict[str, Any]] = []
    if store is None or not getattr(ledger, "enabled", False):
        return rows
    # Prefer the tightest attached budget per group for report caps.
    best: dict[str, BudgetWindow] = {}
    try:
        keys = store.list()
    except Exception:
        return rows
    for key in keys:
        try:
            team = store.get_team(key.team_id) if key.team_id else None
            attached = merge_model_group_budgets(key, team)
        except Exception:
            continue
        for group_name, window, _scope in attached:
            existing = best.get(group_name)
            if existing is None or float(window.max_usd) < float(existing.max_usd):
                best[group_name] = window
    seen: set[str] = set()
    for group_name, window in best.items():
        seen.add(group_name)
        spend = spend_for_model_group_window(
            ledger,
            group_name,
            catalog,
            window.duration,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        status = WindowStatus(
            window=window,
            scope="model_group",
            spend=spend,
            quota="usd",
            model_group=group_name,
        )
        rows.append(
            {
                "model_group": group_name,
                "window": window_header_label(window.duration),
                "spend_usd": round(float(spend), 6),
                "budget_usd": round(float(status.limit), 6),
                "remaining_usd": round(float(status.remaining), 6),
                "soft": status.in_soft_band(soft_ratio),
                "exceeded": status.exceeded,
            }
        )
    for group_name in catalog or {}:
        if group_name in seen:
            continue
        spend = spend_for_model_group_window(
            ledger,
            group_name,
            catalog,
            "day",
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        if spend <= 0:
            continue
        rows.append(
            {
                "model_group": group_name,
                "window": "1d",
                "spend_usd": round(float(spend), 6),
                "budget_usd": 0.0,
                "remaining_usd": 0.0,
                "soft": False,
                "exceeded": False,
            }
        )
    return rows

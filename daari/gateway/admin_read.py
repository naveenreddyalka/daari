"""Redacted admin inventories for virtual keys and teams (#1477)."""

from __future__ import annotations

from typing import Any

# Default page size for GET /v1/daari/keys and /teams (#1499).
DEFAULT_INVENTORY_LIMIT = 100
MAX_INVENTORY_LIMIT = 500


def _clamp_page(*, limit: int | None, offset: int | None) -> tuple[int, int]:
    """Normalize limit/offset; default cap is DEFAULT_INVENTORY_LIMIT."""
    try:
        lim = DEFAULT_INVENTORY_LIMIT if limit is None else int(limit)
    except (TypeError, ValueError):
        lim = DEFAULT_INVENTORY_LIMIT
    try:
        off = 0 if offset is None else int(offset)
    except (TypeError, ValueError):
        off = 0
    lim = max(1, min(lim, MAX_INVENTORY_LIMIT))
    off = max(0, off)
    return lim, off


def _page_meta(total: int, *, limit: int, offset: int, returned: int) -> dict[str, Any]:
    return {
        "total": int(total),
        "limit": int(limit),
        "offset": int(offset),
        "has_more": (offset + returned) < total,
    }


def _spend_rows(
    store: Any,
    *,
    key: Any = None,
    team: Any = None,
    ledger: Any = None,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
) -> list[dict[str, Any]]:
    """Current spend vs caps; empty when ledger is off or unavailable."""
    if ledger is None or not getattr(ledger, "enabled", False):
        return []
    if key is None and team is None:
        return []
    try:
        from daari.auth.budgets import budget_status
    except Exception:
        return []

    if key is not None:
        client_id = key.client_id or key.key_id
        team_obj = team
        if team_obj is None and key.team_id and hasattr(store, "get_team"):
            try:
                team_obj = store.get_team(key.team_id)
            except Exception:
                team_obj = None
        team_ids: list[str] = []
        if team_obj is not None and hasattr(store, "team_client_ids"):
            try:
                team_ids = list(store.team_client_ids(team_obj.team_id) or [])
            except Exception:
                team_ids = []
        try:
            statuses = budget_status(
                key,
                team_obj,
                ledger,
                client_id=client_id,
                team_client_ids=team_ids,
                pricing=pricing,
                fallback_per_1k=fallback_per_1k,
            )
        except Exception:
            return []
        return [_status_row(s) for s in statuses]

    # Team-only: synthesize spend from member keys' team-scoped windows.
    if not hasattr(store, "list") or team is None:
        return []
    try:
        members = [k for k in store.list() if getattr(k, "team_id", None) == team.team_id]
    except Exception:
        return []
    if not members:
        # Still report team windows with zero spend when no members.
        return [
            {
                "window": w.duration,
                "quota": "usd" if float(w.max_usd or 0) > 0 else "requests",
                "scope": "team",
                "spend": 0.0,
                "limit": float(w.max_usd or w.max_requests or 0),
            }
            for w in (team.budget_windows or ())
            if float(w.max_usd or 0) > 0 or int(w.max_requests or 0) > 0
        ]
    # Use first member as the budget_status subject (team scopes aggregate).
    sample = members[0]
    return _spend_rows(
        store,
        key=sample,
        team=team,
        ledger=ledger,
        pricing=pricing,
        fallback_per_1k=fallback_per_1k,
    )


def _status_row(status: Any) -> dict[str, Any]:
    quota = getattr(status, "quota", "usd")
    spend = float(status.spend)
    limit = float(status.limit)
    if quota == "requests":
        spend = float(int(spend))
        limit = float(int(limit))
    return {
        "window": status.window.duration,
        "quota": quota,
        "scope": status.scope,
        "spend": round(spend, 6) if quota == "usd" else int(spend),
        "limit": round(limit, 6) if quota == "usd" else int(limit),
    }


def redact_key(key: Any, *, spend: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Public key inventory row — never secrets or hashes."""
    return {
        "key_id": key.key_id,
        "name": key.name,
        "prefix": key.prefix,
        "team_id": key.team_id,
        "team": key.team_name,
        "daily_budget_usd": float(key.daily_budget_usd or 0),
        "monthly_budget_usd": float(key.monthly_budget_usd or 0),
        "budget_windows": [w.as_dict() for w in (key.budget_windows or ())],
        "tier_cap": key.tier_cap,
        "rpm": int(key.rpm or 0),
        "tpm": int(key.tpm or 0),
        "rpd": int(key.rpd or 0),
        "expires_at": key.expires_at,
        "last_used_at": getattr(key, "last_used_at", None),
        "status": key.status() if callable(getattr(key, "status", None)) else "active",
        "client_id": key.client_id,
        "cache_scope": getattr(key, "cache_scope", "global"),
        "priority": getattr(key, "priority", "normal"),
        "spend": list(spend or []),
    }


def redact_team(
    team: Any,
    *,
    key_count: int = 0,
    spend: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Public team inventory row — never secrets or hashes."""
    return {
        "team_id": team.team_id,
        "name": team.name,
        "budget_windows": [w.as_dict() for w in (team.budget_windows or ())],
        "rpm": int(team.rpm or 0),
        "tpm": int(team.tpm or 0),
        "rpd": int(team.rpd or 0),
        "region_pin": getattr(team, "region_pin", None),
        "cache_scope": getattr(team, "cache_scope", "global"),
        "priority": getattr(team, "priority", "normal"),
        "key_count": int(key_count),
        "spend": list(spend or []),
    }


def keys_inventory(
    store: Any,
    *,
    ledger: Any = None,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
    limit: int | None = None,
    offset: int | None = None,
    status: str | None = None,
    idle_days: int | None = None,
) -> dict[str, Any]:
    lim, off = _clamp_page(limit=limit, offset=offset)
    empty = {"keys": [], **_page_meta(0, limit=lim, offset=off, returned=0)}
    if store is None or not getattr(store, "enabled", True) or not hasattr(store, "list"):
        return empty
    try:
        keys = list(store.list() or [])
    except Exception:
        return empty
    if status is not None or idle_days is not None:
        from daari.auth.virtual_keys import filter_virtual_keys

        keys = filter_virtual_keys(keys, status=status, idle_days=idle_days)
    total = len(keys)
    page_keys = keys[off : off + lim]
    rows: list[dict[str, Any]] = []
    for key in page_keys:
        team = None
        if key.team_id and hasattr(store, "get_team"):
            try:
                team = store.get_team(key.team_id)
            except Exception:
                team = None
        spend = _spend_rows(
            store,
            key=key,
            team=team,
            ledger=ledger,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        rows.append(redact_key(key, spend=spend))
    return {"keys": rows, **_page_meta(total, limit=lim, offset=off, returned=len(rows))}


def teams_inventory(
    store: Any,
    *,
    ledger: Any = None,
    pricing: Any = None,
    fallback_per_1k: float = 0.002,
    limit: int | None = None,
    offset: int | None = None,
) -> dict[str, Any]:
    lim, off = _clamp_page(limit=limit, offset=offset)
    empty = {"teams": [], **_page_meta(0, limit=lim, offset=off, returned=0)}
    if store is None or not getattr(store, "enabled", True) or not hasattr(store, "list_teams"):
        return empty
    try:
        teams = list(store.list_teams() or [])
    except Exception:
        return empty
    try:
        all_keys = list(store.list() or []) if hasattr(store, "list") else []
    except Exception:
        all_keys = []
    total = len(teams)
    page_teams = teams[off : off + lim]
    rows: list[dict[str, Any]] = []
    for team in page_teams:
        key_count = sum(1 for k in all_keys if getattr(k, "team_id", None) == team.team_id)
        spend = _spend_rows(
            store,
            team=team,
            ledger=ledger,
            pricing=pricing,
            fallback_per_1k=fallback_per_1k,
        )
        rows.append(redact_team(team, key_count=key_count, spend=spend))
    return {"teams": rows, **_page_meta(total, limit=lim, offset=off, returned=len(rows))}

"""Fleet-wide circuit-breaker inventory and reset (#1932).

Families: ``systemone``, ``frontier``, ``local_pool``, ``mcp_egress``.
"""

from __future__ import annotations

import time
from typing import Any

from daari.router.circuit_breaker import CircuitBreaker


def _opened_at_wall(breaker: CircuitBreaker) -> float | None:
    """Wall-clock open time when known (Redis share or local wall stamp)."""
    wall = getattr(breaker, "opened_at_wall", None)
    if wall is not None:
        return float(wall)
    share_key = getattr(breaker, "share_key", None)
    if not share_key:
        return None
    try:
        from daari.router import breaker_redis

        client = breaker_redis.breaker_redis_client()
        if client is None:
            return None
        raw = client.get(f"daari:breaker:{share_key}")
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        import json

        data = json.loads(raw)
        opened = float(data.get("opened_at") or 0.0)
        return opened if opened > 0 else None
    except Exception:
        return None


def _row(
    *,
    family: str,
    target: str,
    state: str,
    opened_at: float | None = None,
    rejects: int = 0,
    cooldown_seconds: float | None = None,
) -> dict[str, Any]:
    return {
        "family": family,
        "target": target,
        "state": state,
        "opened_at": opened_at,
        "rejects": int(rejects),
        "cooldown_seconds": float(cooldown_seconds)
        if cooldown_seconds is not None
        else None,
    }


def _row_from_breaker(family: str, target: str, breaker: CircuitBreaker) -> dict[str, Any]:
    state = str(getattr(breaker, "state", "closed") or "closed")
    opened_at = _opened_at_wall(breaker) if state == "open" else None
    if state == "open" and opened_at is None and getattr(breaker, "opened_at", None) is not None:
        # Monotonic-only: approximate with now so inventory always has a stamp.
        opened_at = time.time()
    return _row(
        family=family,
        target=target,
        state=state,
        opened_at=opened_at,
        rejects=int(breaker.reject_count()) if hasattr(breaker, "reject_count") else 0,
        cooldown_seconds=float(getattr(breaker, "cooldown_seconds", 30.0) or 30.0),
    )


def collect_breaker_inventory(
    *,
    frontier_slots: list[tuple[str, CircuitBreaker]] | None = None,
    local_slots: list[tuple[str, CircuitBreaker]] | None = None,
    mcp_slots: list[tuple[str, CircuitBreaker]] | None = None,
    include_systemone: bool = True,
) -> list[dict[str, Any]]:
    """Return sorted breaker rows for stats / prometheus / doctor."""
    rows: list[dict[str, Any]] = []
    if include_systemone:
        try:
            from daari.gateway.systemone import breaker_snapshot

            for snap in breaker_snapshot():
                if not isinstance(snap, dict):
                    continue
                state = str(snap.get("state") or "closed")
                rows.append(
                    _row(
                        family="systemone",
                        target=str(snap.get("base") or "systemone"),
                        state=state,
                        opened_at=time.time() if state == "open" else None,
                        rejects=int(snap.get("rejects") or 0),
                        cooldown_seconds=snap.get("cooldown_seconds"),
                    )
                )
        except Exception:
            pass
    for target, breaker in frontier_slots or []:
        rows.append(_row_from_breaker("frontier", str(target), breaker))
    for target, breaker in local_slots or []:
        rows.append(_row_from_breaker("local_pool", str(target), breaker))
    for target, breaker in mcp_slots or []:
        rows.append(_row_from_breaker("mcp_egress", str(target), breaker))
    return sorted(rows, key=lambda r: (str(r["family"]), str(r["target"])))


def inventory_from_ctx(ctx: Any) -> list[dict[str, Any]]:
    """Build inventory from an AppContext (or duck-typed equivalent)."""
    frontier_slots: list[tuple[str, CircuitBreaker]] = []
    frontier = getattr(ctx, "frontier", None)
    slots = getattr(frontier, "slots", None) if frontier is not None else None
    if slots:
        for slot in slots:
            br = getattr(slot, "breaker", None)
            if br is not None:
                frontier_slots.append((str(getattr(slot, "id", "frontier")), br))

    local_slots: list[tuple[str, CircuitBreaker]] = []
    local_pool = getattr(ctx, "local_pool", None)
    if local_pool is not None:
        for slot in getattr(local_pool, "slots", []) or []:
            br = getattr(slot, "breaker", None)
            if br is not None:
                local_slots.append((str(getattr(slot, "id", "local")), br))

    mcp_slots: list[tuple[str, CircuitBreaker]] = []
    providers = getattr(ctx, "providers", None)
    if providers is not None:
        for pid in providers.list_ids():
            if not str(pid).startswith("mcp:"):
                continue
            provider = providers.get(pid)
            br = getattr(provider, "breaker", None)
            if br is None:
                continue
            target = str(pid)[4:] if str(pid).startswith("mcp:") else str(pid)
            mcp_slots.append((target, br))

    return collect_breaker_inventory(
        frontier_slots=frontier_slots,
        local_slots=local_slots,
        mcp_slots=mcp_slots,
        include_systemone=True,
    )


def reset_breakers(
    ctx: Any | None = None,
    *,
    family: str | None = None,
    target: str | None = None,
    frontier_slots: list[tuple[str, CircuitBreaker]] | None = None,
    local_slots: list[tuple[str, CircuitBreaker]] | None = None,
    mcp_slots: list[tuple[str, CircuitBreaker]] | None = None,
) -> list[dict[str, Any]]:
    """Close matching breakers; return post-reset inventory."""
    fam = (family or "").strip().lower() or None
    tgt = (target or "").strip() or None

    if ctx is not None:
        inventory_before = inventory_from_ctx(ctx)
        # Materialize slot lists from ctx for reset.
        frontier = getattr(ctx, "frontier", None)
        frontier_slots = []
        for slot in getattr(frontier, "slots", None) or []:
            br = getattr(slot, "breaker", None)
            if br is not None:
                frontier_slots.append((str(getattr(slot, "id", "frontier")), br))
        local_pool = getattr(ctx, "local_pool", None)
        local_slots = []
        for slot in getattr(local_pool, "slots", None) or []:
            br = getattr(slot, "breaker", None)
            if br is not None:
                local_slots.append((str(getattr(slot, "id", "local")), br))
        providers = getattr(ctx, "providers", None)
        mcp_slots = []
        if providers is not None:
            for pid in providers.list_ids():
                if not str(pid).startswith("mcp:"):
                    continue
                provider = providers.get(pid)
                br = getattr(provider, "breaker", None)
                if br is not None:
                    mcp_slots.append((str(pid)[4:], br))
        _ = inventory_before

    def _match(family_name: str, target_name: str) -> bool:
        if fam is not None and fam != family_name:
            return False
        if tgt is not None and tgt != target_name:
            return False
        return True

    if fam is None or fam == "systemone":
        if tgt is None:
            from daari.gateway.systemone import close_systemone_breakers

            close_systemone_breakers()
        else:
            from daari.gateway.systemone import breaker_for

            try:
                breaker_for(tgt).record_success()
            except Exception:
                pass

    for name, breaker in frontier_slots or []:
        if _match("frontier", name):
            breaker.record_success()
    for name, breaker in local_slots or []:
        if _match("local_pool", name):
            breaker.record_success()
    for name, breaker in mcp_slots or []:
        if _match("mcp_egress", name):
            breaker.record_success()

    if ctx is not None:
        return inventory_from_ctx(ctx)
    return collect_breaker_inventory(
        frontier_slots=frontier_slots,
        local_slots=local_slots,
        mcp_slots=mcp_slots,
        include_systemone=True,
    )

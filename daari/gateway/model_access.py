"""Gateway 403 when a request model is outside the key/team allowlist (#708)."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from daari.auth.model_access import (
    denial_body,
    model_permitted,
    patterns_from_claims,
    record_model_denial,
)
from daari.gateway.request_log import log_gateway_event

_LOCAL_TIER_CAPS = frozenset({"L3", "L4", "L5"})


def bind_model_patterns(meta: Any, claims: Any, catalog: dict[str, list[str]] | None) -> None:
    key_patterns, team_patterns = patterns_from_claims(claims, catalog)
    meta.key_model_patterns = key_patterns
    meta.team_model_patterns = team_patterns


def reject_frontier_passthrough(request: Any) -> JSONResponse | None:
    """403 when no_frontier or a local tier_cap forbids L6-only routes (#1058)."""
    headers = getattr(request, "headers", None)
    header_flag = ""
    if headers is not None:
        header_flag = str(headers.get("x-daari-no-frontier") or "").strip().lower()
    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    cap = ""
    meta_flag = False
    if claims is not None:
        cap = str(getattr(claims, "tier_cap", None) or "").strip().upper()
        virtual_key = getattr(claims, "virtual_key", None)
        metadata = getattr(virtual_key, "metadata", None) or {}
        if isinstance(metadata, dict) and metadata.get("no_frontier") is True:
            meta_flag = True
    if header_flag != "true" and cap not in _LOCAL_TIER_CAPS and not meta_flag:
        return None
    reason = "no_frontier" if header_flag == "true" or meta_flag else f"tier_cap:{cap}"
    log_gateway_event("frontier_not_allowed", {"reason": reason, "path": getattr(getattr(request, "url", None), "path", "") or ""})
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "type": "frontier_not_allowed",
                "code": "frontier_not_allowed",
                "message": "Frontier (L6) is not permitted for this key.",
            }
        },
    )


def reject_disallowed_model(
    request: Any,
    model: str,
    settings: Any,
    meta: Any = None,
) -> JSONResponse | None:
    """Return a 403 response, or None when the model is allowed.

    Unset allowlists (both sides None) keep today's unrestricted behavior.
    """
    claims = getattr(request.state, "auth_claims", None)
    catalog = getattr(settings, "model_groups", None) or {}
    if meta is not None and (
        getattr(meta, "key_model_patterns", None) is not None
        or getattr(meta, "team_model_patterns", None) is not None
    ):
        key_patterns = meta.key_model_patterns
        team_patterns = meta.team_model_patterns
    else:
        key_patterns, team_patterns = patterns_from_claims(claims, catalog)
        if meta is not None:
            meta.key_model_patterns = key_patterns
            meta.team_model_patterns = team_patterns
    name = (model or "").strip()
    if model_permitted(name, key_patterns=key_patterns, team_patterns=team_patterns):
        return None
    key_id = getattr(claims, "key_id", None)
    client_id = getattr(claims, "client_id", None)
    path = getattr(getattr(request, "url", None), "path", "") or ""
    record_model_denial(
        settings,
        model=name,
        key_id=key_id,
        client_id=client_id,
        path=path,
    )
    log_gateway_event(
        "model_not_allowed",
        {"model": name, "key_id": key_id, "path": path},
    )
    return JSONResponse(status_code=403, content=denial_body(name))


def reject_model_group_budget(
    request: Any,
    model: str,
    settings: Any,
) -> JSONResponse | None:
    """402 when a named model_group shared USD window is exceeded (#1109).

    Soft band sets ``request.state.budget_soft`` and budget headers for the
    tightest model_group window; hard reject happens before L6 escalation.
    """
    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return None
    key = getattr(claims, "virtual_key", None)
    if key is None:
        return None
    from daari.auth.budgets import (
        budget_error,
        model_group_budget_status,
        model_group_budgets_of,
        tightest_window,
    )
    from daari.auth.model_access import groups_for_model
    from daari.gateway.budget_headers import budget_headers, retry_after_seconds

    # Fast path: no attached group budgets and model outside catalog → skip.
    store = getattr(getattr(request, "app", None).state if getattr(request, "app", None) else None, "virtual_key_store", None)
    team = None
    if store is not None and getattr(key, "team_id", None):
        team = store.get_team(key.team_id)
    if claims is not None and getattr(claims, "selected_team_id", None) and store is not None:
        team = store.get_team(claims.selected_team_id) or team
    if not model_group_budgets_of(key) and not model_group_budgets_of(team):
        return None
    catalog = getattr(settings, "model_groups", None) or {}
    if not groups_for_model(model, catalog):
        return None
    ctx = getattr(getattr(request, "app", None), "state", None)
    router = getattr(getattr(ctx, "ctx", None), "router", None) if ctx is not None else None
    ledger = getattr(router, "usage_ledger", None) if router is not None else None
    if ledger is None or not getattr(ledger, "enabled", False):
        return None
    client = (
        getattr(claims, "client_id", None)
        or getattr(key, "client_id", None)
        or getattr(claims, "key_id", None)
        or ""
    )
    pricing = getattr(settings, "pricing", None)
    fallback = float(getattr(getattr(settings, "usage", None), "frontier_price_per_1k_tokens", 0.002) or 0.002)
    statuses = model_group_budget_status(
        model,
        key,
        team,
        ledger,
        catalog=catalog,
        client_id=str(client),
        pricing=pricing,
        fallback_per_1k=fallback,
    )
    if not statuses:
        return None
    exceeded = next((status for status in statuses if status.exceeded), None)
    if exceeded is not None:
        headers = budget_headers(exceeded)
        headers["Retry-After"] = str(retry_after_seconds(exceeded))
        metrics = getattr(getattr(ctx, "ctx", None), "metrics", None) if ctx is not None else None
        if metrics is not None and hasattr(metrics, "record_reject"):
            metrics.record_reject("budget")
        log_gateway_event(
            "model_group_budget_exceeded",
            {
                "model": (model or "").strip(),
                "model_group": exceeded.model_group,
                "client_id": client,
            },
        )
        return JSONResponse(
            status_code=402,
            content={
                "error": budget_error(
                    client_id=str(client),
                    window=exceeded.window,
                    spend=exceeded.spend,
                    scope=exceeded.scope,
                    limit_usd=exceeded.limit,
                    model_group=exceeded.model_group,
                )
            },
            headers=headers,
        )
    soft_ratio = float(getattr(getattr(settings, "frontier", None), "soft_budget_ratio", 0.8) or 0.0)
    tightest = tightest_window(statuses)
    if tightest is not None and tightest.in_soft_band(soft_ratio):
        request.state.budget_soft = True
        # Overlay model_group budget headers so soft warning is visible.
        existing = getattr(request.state, "budget_response_headers", None) or {}
        merged = {**existing, **budget_headers(tightest, soft=True)}
        request.state.budget_response_headers = merged
    return None


def reject_model_max_budget(
    request: Any,
    model: str,
    settings: Any,
) -> JSONResponse | None:
    """402 when a team/key model_max_budget pattern window is exceeded (#1113)."""
    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    if claims is None or getattr(claims, "kind", None) != "virtual":
        return None
    key = getattr(claims, "virtual_key", None)
    if key is None:
        return None
    from daari.auth.budgets import (
        budget_error,
        effective_model_max_budget,
        model_max_budget_status,
        tightest_window,
    )
    from daari.gateway.budget_headers import budget_headers, retry_after_seconds

    store = getattr(
        getattr(request, "app", None).state if getattr(request, "app", None) else None,
        "virtual_key_store",
        None,
    )
    team = None
    team_ids: list[str] = []
    if store is not None and getattr(key, "team_id", None):
        team = store.get_team(key.team_id)
    if claims is not None and getattr(claims, "selected_team_id", None) and store is not None:
        team = store.get_team(claims.selected_team_id) or team
    if team is not None and store is not None and hasattr(store, "team_client_ids"):
        team_ids = store.team_client_ids(team.team_id)
    if not effective_model_max_budget(key, team):
        return None
    ctx = getattr(getattr(request, "app", None), "state", None)
    router = getattr(getattr(ctx, "ctx", None), "router", None) if ctx is not None else None
    ledger = getattr(router, "usage_ledger", None) if router is not None else None
    if ledger is None or not getattr(ledger, "enabled", False):
        return None
    client = (
        getattr(claims, "client_id", None)
        or getattr(key, "client_id", None)
        or getattr(claims, "key_id", None)
        or ""
    )
    pricing = getattr(settings, "pricing", None)
    fallback = float(
        getattr(getattr(settings, "usage", None), "frontier_price_per_1k_tokens", 0.002) or 0.002
    )
    statuses = model_max_budget_status(
        model,
        key,
        team,
        ledger,
        client_id=str(client),
        team_client_ids=team_ids,
        pricing=pricing,
        fallback_per_1k=fallback,
    )
    if not statuses:
        return None
    exceeded = next((status for status in statuses if status.exceeded), None)
    if exceeded is not None:
        headers = budget_headers(exceeded)
        headers["Retry-After"] = str(retry_after_seconds(exceeded))
        metrics = getattr(getattr(ctx, "ctx", None), "metrics", None) if ctx is not None else None
        if metrics is not None and hasattr(metrics, "record_reject"):
            metrics.record_reject("budget")
        log_gateway_event(
            "model_max_budget_exceeded",
            {
                "model": (model or "").strip(),
                "model_pattern": exceeded.model_pattern,
                "client_id": client,
            },
        )
        return JSONResponse(
            status_code=402,
            content={
                "error": budget_error(
                    client_id=str(client),
                    window=exceeded.window,
                    spend=exceeded.spend,
                    scope=exceeded.scope,
                    limit_usd=exceeded.limit,
                    model_pattern=exceeded.model_pattern,
                )
            },
            headers=headers,
        )
    soft_ratio = float(getattr(getattr(settings, "frontier", None), "soft_budget_ratio", 0.8) or 0.0)
    tightest = tightest_window(statuses)
    if tightest is not None and tightest.in_soft_band(soft_ratio):
        request.state.budget_soft = True
        existing = getattr(request.state, "budget_response_headers", None) or {}
        merged = {**existing, **budget_headers(tightest, soft=True)}
        request.state.budget_response_headers = merged
    return None

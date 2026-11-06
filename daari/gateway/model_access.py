"""Gateway 403 when a request model is outside the key/team allowlist (#708)."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from daari.auth.model_access import (
    denial_body,
    model_permitted,
    patterns_from_claims,
    record_model_denial,
    record_retired_denial,
)
from daari.gateway.request_log import log_gateway_event

_LOCAL_TIER_CAPS = frozenset({"L3", "L4", "L5"})


def bind_model_patterns(meta: Any, claims: Any, catalog: dict[str, list[str]] | None) -> None:
    key_patterns, team_patterns = patterns_from_claims(claims, catalog)
    meta.key_model_patterns = key_patterns
    meta.team_model_patterns = team_patterns


def cloud_egress_blocked_response(exc: Any) -> JSONResponse:
    """403/400 when a local-only fence refuses an Ollama :cloud hop (#1736)."""
    reason = str(getattr(exc, "reason", "") or "no_frontier")
    if reason == "region_pin":
        return JSONResponse(
            status_code=400,
            content={
                "error": {
                    "type": "region_unavailable",
                    "code": "region_pin",
                    "message": "Ollama cloud models cannot satisfy region_pin.",
                }
            },
        )
    return JSONResponse(
        status_code=403,
        content={
            "error": {
                "type": "frontier_not_allowed",
                "code": reason,
                "message": "Frontier (L6) is not permitted for this key.",
            }
        },
    )


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


def retired_model_error(model: str) -> dict[str, str]:
    name = (model or "").strip()
    return {
        "type": "model_retired",
        "code": "model_retired",
        "message": f"Model '{name}' is retired and cannot be used.",
    }


def deny_retired_model(
    request: Any,
    model: str,
    settings: Any,
) -> dict[str, str] | None:
    """Audit + Prometheus for a retired id, or None when the request may proceed."""
    models = getattr(settings, "models", None)
    if models is not None and getattr(models, "reject_retired", True) is False:
        return None
    from daari.router.capabilities import anthropic_lifecycle_fields

    name = (model or "").strip()
    if not name:
        return None
    stage = anthropic_lifecycle_fields(name, settings).get("lifecycle") or "active"
    if stage != "retired":
        return None
    path = getattr(getattr(request, "url", None), "path", "") or ""
    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    key_id = getattr(claims, "key_id", None) if claims is not None else None
    client_id = getattr(claims, "client_id", None) if claims is not None else None
    team_id = None
    if claims is not None:
        team_id = getattr(claims, "selected_team_id", None)
        if not team_id:
            virtual_key = getattr(claims, "virtual_key", None)
            team_id = getattr(virtual_key, "team_id", None) if virtual_key is not None else None
    record_retired_denial(
        settings,
        model=name,
        key_id=key_id,
        client_id=client_id,
        team_id=team_id,
        path=path,
    )
    app_state = getattr(getattr(request, "app", None), "state", None)
    metrics = getattr(getattr(app_state, "ctx", None), "metrics", None) if app_state else None
    if metrics is not None and hasattr(metrics, "record_reject"):
        metrics.record_reject("retired")
    log_gateway_event(
        "model_retired",
        {"model": name, "path": path, "key_id": key_id, "team_id": team_id},
    )
    return retired_model_error(name)


def reject_retired_model(
    request: Any,
    model: str,
    settings: Any,
) -> JSONResponse | None:
    """410 when catalog lifecycle is retired and models.reject_retired (#1521)."""
    error = deny_retired_model(request, model, settings)
    if error is None:
        return None
    return JSONResponse(status_code=410, content={"error": error})


def reject_deprecated_anthropic_speed(
    model: str | None,
    speed: str | None,
    settings: Any,
) -> JSONResponse | None:
    """400 when a removed model+speed combo is requested without degrade (#2053)."""
    from daari.pricing import resolve_anthropic_speed_lifecycle

    decision = resolve_anthropic_speed_lifecycle(
        model=model, speed=speed, settings=settings
    )
    if decision.action != "reject" or not decision.reject_detail:
        return None
    log_gateway_event(
        "deprecated_speed_rejected",
        {"model": model, "speed": speed, "detail": decision.reject_detail},
    )
    return JSONResponse(
        status_code=400,
        content={
            "detail": decision.reject_detail,
            "error": {
                "type": "invalid_request_error",
                "code": "deprecated_speed_removed",
                "message": decision.reject_detail,
            },
        },
    )


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


def _team_for_claims(request: Any, claims: Any) -> Any:
    vk = getattr(claims, "virtual_key", None) if claims is not None else None
    team_id = getattr(claims, "selected_team_id", None) if claims is not None else None
    if not team_id and vk is not None:
        team_id = getattr(vk, "team_id", None)
    if not team_id:
        return None
    store = getattr(getattr(request, "app", None), "state", None)
    store = getattr(store, "virtual_key_store", None) if store is not None else None
    if store is None or not getattr(store, "enabled", False):
        return None
    return store.get_team(team_id)


def reject_disallowed_service_tier(
    request: Any,
    *,
    service_tier: str | None = None,
    speed: str | None = None,
) -> JSONResponse | None:
    """403 when service_tier/speed is outside the key∩team allowlist (#2070).

    Opt-in degrade (key or team ``degrade_disallowed_service_tier``) clears the
    disallowed field(s) on ``request.state`` for the caller to apply, sets
    ``request.state.service_tier_allowlist_warning``, and returns None.
    """
    from daari.auth.service_tier_access import (
        denial_body,
        effective_allowed_service_tiers,
        effective_degrade,
        normalize_tier_name,
        service_tier_permitted,
    )

    claims = getattr(getattr(request, "state", None), "auth_claims", None)
    vk = getattr(claims, "virtual_key", None) if claims is not None else None
    if vk is None:
        return None
    team = _team_for_claims(request, claims)
    allowed = effective_allowed_service_tiers(
        getattr(vk, "allowed_service_tiers", None),
        getattr(team, "allowed_service_tiers", None) if team is not None else None,
    )
    if allowed is None:
        return None
    degrade = effective_degrade(
        bool(getattr(vk, "degrade_disallowed_service_tier", False)),
        bool(getattr(team, "degrade_disallowed_service_tier", False)) if team is not None else False,
    )
    tier_name = normalize_tier_name(service_tier)
    speed_name = normalize_tier_name(speed)
    violations: list[tuple[str, str]] = []
    if tier_name and not service_tier_permitted(tier_name, allowed=allowed):
        violations.append(("service_tier", tier_name))
    if speed_name and not service_tier_permitted(speed_name, allowed=allowed):
        violations.append(("speed", speed_name))
    if not violations:
        return None
    field, value = violations[0]
    key_id = getattr(claims, "key_id", None)
    path = getattr(getattr(request, "url", None), "path", "") or ""
    app_state = getattr(getattr(request, "app", None), "state", None)
    metrics = getattr(getattr(app_state, "ctx", None), "metrics", None) if app_state else None
    if degrade:
        clear_tier = any(item[0] == "service_tier" for item in violations)
        clear_speed = any(item[0] == "speed" for item in violations)
        request.state.service_tier_allowlist_clear_tier = clear_tier
        request.state.service_tier_allowlist_clear_speed = clear_speed
        request.state.service_tier_allowlist_warning = "service_tier_not_allowed_degraded"
        if metrics is not None and hasattr(metrics, "record_soft_warning"):
            metrics.record_soft_warning("service_tier_not_allowed_degraded")
        log_gateway_event(
            "service_tier_not_allowed",
            {
                "field": field,
                "value": value,
                "key_id": key_id,
                "path": path,
                "action": "degrade",
            },
        )
        return None
    if metrics is not None and hasattr(metrics, "record_reject"):
        metrics.record_reject("service_tier_not_allowed")
    log_gateway_event(
        "service_tier_not_allowed",
        {
            "field": field,
            "value": value,
            "key_id": key_id,
            "path": path,
            "action": "deny",
        },
    )
    return JSONResponse(
        status_code=403,
        content=denial_body(requested=value, field=field),
    )


def apply_service_tier_allowlist_degrade(body: Any, request: Any, internal: Any = None) -> None:
    """Apply opt-in clear + gate_warning after a degrade decision (#2070)."""
    warning = getattr(getattr(request, "state", None), "service_tier_allowlist_warning", None)
    if not warning:
        return
    if getattr(request.state, "service_tier_allowlist_clear_tier", False) and hasattr(
        body, "service_tier"
    ):
        body.service_tier = None
    if getattr(request.state, "service_tier_allowlist_clear_speed", False) and hasattr(
        body, "speed"
    ):
        body.speed = None
    if internal is not None:
        sampling = getattr(internal, "sampling", None)
        if sampling is not None:
            if getattr(request.state, "service_tier_allowlist_clear_tier", False):
                sampling.service_tier = None
            if getattr(request.state, "service_tier_allowlist_clear_speed", False):
                sampling.speed = None
            existing = getattr(sampling, "gate_warning", None)
            if existing and warning in existing:
                return
            sampling.gate_warning = f"{existing}; {warning}" if existing else warning

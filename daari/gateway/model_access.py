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

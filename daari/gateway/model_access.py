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


def bind_model_patterns(meta: Any, claims: Any, catalog: dict[str, list[str]] | None) -> None:
    key_patterns, team_patterns = patterns_from_claims(claims, catalog)
    meta.key_model_patterns = key_patterns
    meta.team_model_patterns = team_patterns


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

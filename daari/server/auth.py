"""Resolve Bearer / x-api-key into master or virtual-key claims (issue #111)."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from daari.auth.virtual_keys import VirtualKey, VirtualKeyStore, effective_cache_scope


@dataclass
class AuthClaims:
    kind: str  # master | virtual
    key_id: str | None = None
    client_id: str | None = None
    tier_cap: str | None = None
    daily_budget_usd: float = 0.0
    monthly_budget_usd: float = 0.0
    virtual_key: VirtualKey | None = None
    boundary_profile: str | None = None
    region_pin: str | None = None
    # Raw allowlist (#708). Expanded against settings.model_groups at request time.
    allowed_models: tuple[str, ...] | None = None
    model_groups: tuple[str, ...] | None = None
    team_allowed_models: tuple[str, ...] | None = None
    team_model_groups: tuple[str, ...] | None = None
    # Effective cache isolation for this token (#768). global | team | key.
    cache_scope: str = "global"
    # Request-time team selection (#1107). None = key-pinned / default.
    selected_team_id: str | None = None


def extract_api_key(headers: Any) -> str:
    supplied = headers.get("x-api-key", "") or ""
    if not supplied:
        authorization = headers.get("authorization", "") or ""
        if authorization.lower().startswith("bearer "):
            supplied = authorization[len("bearer ") :].strip()
    return supplied


def normalize_master_keys(master_key: str | list[str] | None) -> list[str]:
    """Accepted master secrets. A string stays one key; a list is an overlap set."""
    if master_key is None:
        return []
    items = [master_key] if isinstance(master_key, str) else list(master_key)
    keys: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            keys.append(text)
    return keys


def _constant_time_equals(supplied: str, candidate: str) -> bool:
    left = supplied.encode("utf-8")
    right = candidate.encode("utf-8")
    if len(left) != len(right):
        hmac.compare_digest(left, left)
        return False
    return hmac.compare_digest(left, right)


def master_key_matches(supplied: str, master_key: str | list[str] | None) -> bool:
    """True if `supplied` equals any configured master key. Checks every key."""
    if not supplied:
        return False
    matched = False
    for key in normalize_master_keys(master_key):
        matched = _constant_time_equals(supplied, key) or matched
    return matched


def apply_auth_claims_to_meta(
    meta: Any,
    claims: AuthClaims | None,
    *,
    model_groups: dict | None = None,
) -> None:
    """Fill RequestMeta defaults from a virtual key; explicit headers win."""
    if claims is None or claims.kind != "virtual":
        return
    if not meta.client_id and claims.client_id:
        meta.client_id = claims.client_id
    if not meta.tier_cap and claims.tier_cap:
        meta.tier_cap = claims.tier_cap
    if not getattr(meta, "boundary_profile", None) and claims.boundary_profile:
        meta.boundary_profile = claims.boundary_profile
    if not getattr(meta, "region_pin", None) and claims.region_pin:
        meta.region_pin = claims.region_pin
    from daari.auth.model_access import patterns_from_claims

    key_patterns, team_patterns = patterns_from_claims(claims, model_groups)
    meta.key_model_patterns = key_patterns
    meta.team_model_patterns = team_patterns
    if not getattr(meta, "key_id", None) and claims.key_id:
        meta.key_id = claims.key_id
    team_id = getattr(getattr(claims, "virtual_key", None), "team_id", None)
    selected = getattr(claims, "selected_team_id", None)
    if selected:
        team_id = selected
    if not getattr(meta, "team_id", None) and team_id:
        meta.team_id = team_id
    scope = getattr(claims, "cache_scope", None) or "global"
    if scope in {"team", "key"}:
        meta.cache_scope = scope


TEAM_HEADER = "x-daari-team"


def membership_subject(key: VirtualKey) -> str:
    """Stable subject for team entitlements: SSO sub, else client_id, else key_id."""
    meta = key.metadata or {}
    for field in ("sso_sub", "sub", "subject"):
        raw = meta.get(field)
        if raw:
            return str(raw).strip()
    return (key.client_id or key.key_id or "").strip()


def key_allows_team_override(key: VirtualKey) -> bool:
    meta = key.metadata or {}
    return bool(meta.get("allow_team_override"))


def resolve_team_header(
    headers: Any,
    claims: AuthClaims,
    store: VirtualKeyStore | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """Apply optional ``X-Daari-Team`` selection (#1107).

    Returns ``(selected_team_id, error_payload)``. ``error_payload`` is set on
    403 cases (non-member or pinned-team override refused).
    """
    if claims.kind != "virtual" or claims.virtual_key is None or store is None:
        return None, None
    raw = ""
    if headers is not None:
        raw = str(headers.get(TEAM_HEADER) or headers.get("X-Daari-Team") or "").strip()
    if not raw:
        return None, None
    key = claims.virtual_key
    pinned = (key.team_id or "").strip()
    # Resolve name or id.
    team = store.get_team(raw) or store.get_team(name=raw)
    if team is None:
        return None, {
            "type": "permission_error",
            "code": "team_not_found",
            "message": f"Unknown team {raw!r}.",
        }
    wanted = team.team_id
    if pinned and wanted != pinned and not key_allows_team_override(key):
        return None, {
            "type": "permission_error",
            "code": "team_override_denied",
            "message": (
                "Virtual key is pinned to a team; set metadata.allow_team_override "
                "to select another."
            ),
        }
    subject = membership_subject(key)
    if not store.is_team_member(subject, wanted):
        return None, {
            "type": "permission_error",
            "code": "team_membership_required",
            "message": "Authenticated identity is not a member of the requested team.",
        }
    return wanted, None


def apply_selected_team(
    claims: AuthClaims,
    team_id: str,
    store: VirtualKeyStore,
) -> None:
    """Stamp ``selected_team_id`` and refresh team allowlist fields on claims."""
    claims.selected_team_id = team_id
    team = store.get_team(team_id)
    if team is None:
        return
    claims.team_allowed_models = team.allowed_models
    claims.team_model_groups = team.model_groups
    team_scope = team.cache_scope
    key_scope = getattr(claims.virtual_key, "cache_scope", "global") if claims.virtual_key else "global"
    claims.cache_scope = effective_cache_scope(key_scope, team_scope)
    if not claims.region_pin and team.region_pin:
        claims.region_pin = team.region_pin


def resolve_auth(
    supplied: str,
    *,
    master_key: str | list[str] | None,
    store: VirtualKeyStore | None,
) -> AuthClaims | None:
    """Return claims when the key is valid, else None."""
    if master_key_matches(supplied, master_key):
        return AuthClaims(kind="master")
    if store is not None and store.enabled and supplied:
        key = store.resolve(supplied)
        if key is not None:
            if key.is_expired():
                return AuthClaims(
                    kind="expired",
                    key_id=key.key_id,
                    client_id=key.client_id or key.key_id,
                    virtual_key=key,
                )
            region_pin = key.region_pin
            team_allowed = None
            team_groups = None
            team_scope = "global"
            if key.team_id:
                team = store.get_team(key.team_id)
                if team is not None:
                    if not region_pin and team.region_pin:
                        region_pin = team.region_pin
                    team_allowed = team.allowed_models
                    team_groups = team.model_groups
                    team_scope = team.cache_scope
            return AuthClaims(
                kind="virtual",
                key_id=key.key_id,
                client_id=key.client_id or key.key_id,
                tier_cap=key.tier_cap,
                daily_budget_usd=key.daily_budget_usd,
                monthly_budget_usd=key.monthly_budget_usd,
                virtual_key=key,
                boundary_profile=(key.metadata or {}).get("boundary_profile"),
                region_pin=region_pin,
                allowed_models=key.allowed_models,
                model_groups=key.model_groups,
                team_allowed_models=team_allowed,
                team_model_groups=team_groups,
                cache_scope=effective_cache_scope(key.cache_scope, team_scope),
            )
    # Auth required but nothing matched.
    if normalize_master_keys(master_key) or (store is not None and store.enabled and store.list()):
        return None
    # No master key and no virtual keys configured → open.
    return AuthClaims(kind="master")


def _team_cache_scope(store: VirtualKeyStore | None, team_id: str | None) -> str:
    if store is None or not team_id or not store.enabled:
        return "global"
    team = store.get_team(team_id)
    if team is None:
        return "global"
    return team.cache_scope


def introspect_token(
    token: str,
    *,
    master_key: str | list[str] | None,
    store: VirtualKeyStore | None,
) -> dict[str, Any]:
    """RFC 7662 introspection payload for a token (#618). Never returns secrets."""
    supplied = (token or "").strip()
    if not supplied:
        return {"active": False}
    if master_key_matches(supplied, master_key):
        return {
            "active": True,
            "username": "master",
            "token_type": "master",
        }
    if store is None or not store.enabled:
        return {"active": False}
    key = store.resolve(supplied)
    if key is None:
        return {"active": False}
    if key.is_expired():
        return {"active": False}
    payload: dict[str, Any] = {
        "active": True,
        "client_id": key.client_id or key.key_id,
        "username": key.name,
        "token_type": "virtual",
    }
    if key.expires_at:
        try:
            exp = datetime.fromisoformat(key.expires_at.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            payload["exp"] = int(exp.timestamp())
        except ValueError:
            pass
    if key.team_id:
        payload["team_id"] = key.team_id
    if key.team_name:
        payload["team_name"] = key.team_name
    if key.tier_cap:
        payload["tier_cap"] = key.tier_cap
    if int(key.rpm or 0) > 0:
        payload["rpm"] = int(key.rpm)
    if int(key.tpm or 0) > 0:
        payload["tpm"] = int(key.tpm)
    if int(key.rpd or 0) > 0:
        payload["rpd"] = int(key.rpd)
    payload["cache_scope"] = effective_cache_scope(
        key.cache_scope,
        _team_cache_scope(store, key.team_id),
    )
    return payload

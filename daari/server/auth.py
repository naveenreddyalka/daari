"""Resolve Bearer / x-api-key into master or virtual-key claims (issue #111)."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from daari.auth.virtual_keys import VirtualKey, VirtualKeyStore


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


def extract_api_key(headers: Any) -> str:
    supplied = headers.get("x-api-key", "") or ""
    if not supplied:
        authorization = headers.get("authorization", "") or ""
        if authorization.lower().startswith("bearer "):
            supplied = authorization[len("bearer ") :].strip()
    return supplied


def apply_auth_claims_to_meta(meta: Any, claims: AuthClaims | None) -> None:
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


def resolve_auth(
    supplied: str,
    *,
    master_key: str,
    store: VirtualKeyStore | None,
) -> AuthClaims | None:
    """Return claims when the key is valid, else None."""
    if master_key and hmac.compare_digest(supplied, master_key):
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
            if not region_pin and key.team_id:
                team = store.get_team(key.team_id)
                if team is not None and team.region_pin:
                    region_pin = team.region_pin
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
            )
    # Auth required but nothing matched.
    if master_key or (store is not None and store.enabled and store.list()):
        return None
    # No master key and no virtual keys configured → open.
    return AuthClaims(kind="master")


def introspect_token(
    token: str,
    *,
    master_key: str,
    store: VirtualKeyStore | None,
) -> dict[str, Any]:
    """RFC 7662 introspection payload for a token (#618). Never returns secrets."""
    supplied = (token or "").strip()
    if not supplied:
        return {"active": False}
    if master_key and hmac.compare_digest(supplied, master_key):
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
    return payload

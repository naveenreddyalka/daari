"""Resolve Bearer / x-api-key into master or virtual-key claims (issue #111)."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
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
            return AuthClaims(
                kind="virtual",
                key_id=key.key_id,
                client_id=key.client_id or key.key_id,
                tier_cap=key.tier_cap,
                daily_budget_usd=key.daily_budget_usd,
                monthly_budget_usd=key.monthly_budget_usd,
                virtual_key=key,
            )
    # Auth required but nothing matched.
    if master_key or (store is not None and store.enabled and store.list()):
        return None
    # No master key and no virtual keys configured → open.
    return AuthClaims(kind="master")

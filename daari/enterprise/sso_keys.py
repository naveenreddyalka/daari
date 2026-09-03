"""IdP claim → virtual-key policy sync (issue #176)."""

from __future__ import annotations

from typing import Any

from daari.auth.virtual_keys import BudgetWindow, VirtualKey, VirtualKeyStore
from daari.enterprise.audit import AuditLog
from daari.enterprise.config import SsoKeyPolicy, SsoSettings

DEFAULT_CLAIM = "__default__"


class UnmappedSsoPolicy(Exception):
    """No key_mappings hit and deny_unmapped is set (or no default)."""


def claim_values(claims: dict[str, Any], mapping_claim: str) -> list[str]:
    raw = claims.get(mapping_claim)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    value = str(raw).strip()
    return [value] if value else []


def resolve_policy(
    claims: dict[str, Any], sso: SsoSettings
) -> tuple[str | None, SsoKeyPolicy | None]:
    mappings = sso.key_mappings or {}
    for value in claim_values(claims, sso.mapping_claim):
        if value in mappings:
            return value, mappings[value]
    if sso.default_policy is not None:
        return DEFAULT_CLAIM, sso.default_policy
    if mappings or sso.deny_unmapped:
        return None, None
    return DEFAULT_CLAIM, SsoKeyPolicy()


def _windows(policy: SsoKeyPolicy) -> list[BudgetWindow]:
    out: list[BudgetWindow] = []
    for item in policy.budget_windows or []:
        if not isinstance(item, dict):
            continue
        duration = str(item.get("duration") or "").strip()
        try:
            max_usd = float(item.get("max_usd") or 0)
        except (TypeError, ValueError):
            continue
        if duration and max_usd > 0:
            out.append(BudgetWindow(duration, max_usd))
    return out


def _metadata(sso: SsoSettings, claim_value: str, policy: SsoKeyPolicy) -> dict[str, Any]:
    return {
        "mapping_claim": sso.mapping_claim,
        "claim_value": claim_value,
        "boundary_profile": policy.boundary_profile,
    }


def find_sso_key(store: VirtualKeyStore, subject: str) -> VirtualKey | None:
    client_id = f"sso:{subject}"
    for key in store.list():
        # Expired SSO keys are treated as absent so the next login remints (#331).
        if key.client_id == client_id and not key.revoked and not key.is_expired():
            return key
    return None


def sync_sso_virtual_key(
    store: VirtualKeyStore,
    *,
    subject: str,
    claims: dict[str, Any],
    sso: SsoSettings,
    audit: AuditLog,
    role: str,
) -> dict[str, Any]:
    claim_value, policy = resolve_policy(claims, sso)
    current = set(claim_values(claims, sso.mapping_claim))
    existing = find_sso_key(store, subject)

    if existing is not None:
        stored = (existing.metadata or {}).get("claim_value")
        if stored and stored != DEFAULT_CLAIM and stored not in current:
            store.revoke(existing.key_id)
            audit.record(
                actor=subject,
                role=role,
                action="sso.revoke_virtual_key",
                detail={
                    "key_id": existing.key_id,
                    "mapping_claim": sso.mapping_claim,
                    "claim_value": stored,
                },
            )
            existing = None

    if policy is None:
        if existing is not None:
            store.revoke(existing.key_id)
            audit.record(
                actor=subject,
                role=role,
                action="sso.revoke_virtual_key",
                detail={
                    "key_id": existing.key_id,
                    "mapping_claim": sso.mapping_claim,
                    "claim_value": (existing.metadata or {}).get("claim_value"),
                },
            )
        raise UnmappedSsoPolicy(f"no SSO key policy for {sso.mapping_claim}={list(current)}")

    meta = _metadata(sso, claim_value or DEFAULT_CLAIM, policy)
    if existing is None:
        created = store.create(
            name=f"sso:{subject}",
            client_id=f"sso:{subject}",
            daily_budget_usd=policy.daily_budget_usd,
            monthly_budget_usd=policy.monthly_budget_usd,
            rpm=policy.rpm,
            tpm=policy.tpm,
            tier_cap=policy.tier_cap,
            team=policy.team,
            budget_windows=_windows(policy) or None,
            metadata=meta,
            expires_at=policy.key_ttl,
        )
        audit.record(
            actor=subject,
            role=role,
            action="sso.mint_virtual_key",
            detail={
                "key_id": created.key.key_id,
                "mapping_claim": sso.mapping_claim,
                "claim_value": claim_value,
            },
        )
        return {
            "virtual_key_id": created.key.key_id,
            "virtual_key_prefix": created.key.prefix,
            "virtual_key": created.plaintext,
            "virtual_key_minted": True,
            "claim_value": claim_value,
            "boundary_profile": policy.boundary_profile,
        }

    store.update_limits(
        existing.key_id,
        daily_budget_usd=policy.daily_budget_usd,
        monthly_budget_usd=policy.monthly_budget_usd,
        rpm=policy.rpm,
        tpm=policy.tpm,
        tier_cap=policy.tier_cap,
        team=policy.team,
        budget_windows=_windows(policy) or None,
        metadata=meta,
    )
    return {
        "virtual_key_id": existing.key_id,
        "virtual_key_minted": False,
        "claim_value": claim_value,
        "boundary_profile": policy.boundary_profile,
    }

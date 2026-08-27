from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EnterpriseCacheSettings(BaseModel):
    enabled: bool = False
    share_classes: list[str] = Field(default_factory=list)
    no_org_cache_default: bool = False


class EnterpriseLearningSettings(BaseModel):
    enabled: bool = False
    upload_prompts: bool = False
    upload_code: bool = False


class SsoKeyPolicy(BaseModel):
    """Limits applied to an IdP-minted virtual key (issue #176)."""

    daily_budget_usd: float = 0.0
    monthly_budget_usd: float = 0.0
    rpm: int = 0
    tpm: int = 0
    tier_cap: str | None = None
    team: str | None = None
    boundary_profile: str | None = None
    budget_windows: list[dict[str, Any]] = Field(default_factory=list)


class SsoSettings(BaseModel):
    """OIDC / SSO for admin surfaces (issues #119, #136, #176)."""

    enabled: bool = False
    issuer: str = "daari-dev"
    # Shared secret for mint_dev_token / verify_dev_token (local IdP stub).
    secret: str = ""
    # Production OIDC: explicit JWKS URL and/or discovery document.
    jwks_url: str = ""
    discovery_url: str = ""
    # Expected aud claim (empty = do not verify audience).
    audience: str = ""
    # Claim name used for RBAC (default "role"; also checks daari_role).
    role_claim: str = "role"
    # Require at least this role for /v1/daari/config and audit endpoints.
    admin_min_role: str = "admin"
    # When true, first successful SSO login mints a virtual API key for sub.
    mint_virtual_key_on_login: bool = False
    mapping_claim: str = "groups"
    key_mappings: dict[str, SsoKeyPolicy] = Field(default_factory=dict)
    default_policy: SsoKeyPolicy | None = None
    deny_unmapped: bool = False


class OrgSettings(BaseModel):
    enabled: bool = False
    id: str | None = None
    org_id: str | None = None
    tenant_id: str | None = None  # Backward-compatible alias while docs migrate.
    control_plane_url: str | None = None
    org_token: str | None = None
    shared_cache_url: str | None = None
    shared_cache_token: str | None = None
    shared_cache_require_token: bool = False
    shared_cache_timeout_seconds: float = 1.0
    shared_cache_max_retries: int = 2
    shared_cache_backoff_seconds: float = 0.2
    shared_cache_path: str | None = None
    learning_enabled: bool = False
    learning_url: str | None = None
    learning_token: str | None = None
    learning_timeout_seconds: float = 0.5
    learning_sync_seconds: float = 300.0
    learning_path: str | None = None
    policy_overrides: dict[str, Any] = Field(default_factory=dict)
    profile: str = "developer"
    device_id: str | None = None
    # HMAC secret used to verify X-Daari-Signature on org config fetch.
    config_signing_secret: str = ""
    # Periodic signed org-config refresh URL (extends learning sync).
    policy_sync_url: str | None = None
    cache: EnterpriseCacheSettings = Field(default_factory=EnterpriseCacheSettings)
    learning: EnterpriseLearningSettings = Field(default_factory=EnterpriseLearningSettings)
    sso: SsoSettings = Field(default_factory=SsoSettings)
    audit_path: str = "~/.daari/audit/audit.sqlite3"

    @property
    def resolved_org_id(self) -> str | None:
        return self.org_id or self.id or self.tenant_id

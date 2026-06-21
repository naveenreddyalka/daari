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


class OrgSettings(BaseModel):
    enabled: bool = False
    org_id: str | None = None
    tenant_id: str | None = None  # Backward-compatible alias while docs migrate.
    control_plane_url: str | None = None
    org_token: str | None = None
    shared_cache_path: str | None = None
    policy_overrides: dict[str, Any] = Field(default_factory=dict)
    profile: str = "developer"
    cache: EnterpriseCacheSettings = Field(default_factory=EnterpriseCacheSettings)
    learning: EnterpriseLearningSettings = Field(default_factory=EnterpriseLearningSettings)

    @property
    def resolved_org_id(self) -> str | None:
        return self.org_id or self.tenant_id

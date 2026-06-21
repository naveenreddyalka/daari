from __future__ import annotations

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
    tenant_id: str | None = None
    control_plane_url: str | None = None
    org_token: str | None = None
    profile: str = "developer"
    cache: EnterpriseCacheSettings = Field(default_factory=EnterpriseCacheSettings)
    learning: EnterpriseLearningSettings = Field(default_factory=EnterpriseLearningSettings)

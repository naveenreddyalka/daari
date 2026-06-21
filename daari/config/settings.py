from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from daari.enterprise.config import OrgSettings


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 11435


class ModelsSettings(BaseModel):
    l3: str = "llama3.2:3b"
    l4: str = "llama3.1:8b"
    l5: str = "llama3.1:70b"
    weights: dict[str, dict[str, float]] = Field(default_factory=dict)


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"


class L0CacheSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/cache/l0"


class L1CacheSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/cache/l1"
    similarity_threshold: float = 0.92
    max_entries: int = 1000
    embedding_model: str = "nomic-embed-text"


class CacheSettings(BaseModel):
    l0: L0CacheSettings = Field(default_factory=L0CacheSettings)
    l1: L1CacheSettings = Field(default_factory=L1CacheSettings)


class FrontierSettings(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    confidence_threshold: float = 0.7
    base_url: str = "https://api.openai.com/v1"


class RoutingSettings(BaseModel):
    prefer: str = "balanced"  # latency | accuracy | balanced
    confidence_threshold: float = 0.7


class ToolsSettings(BaseModel):
    unknown: str = "deny"  # deny | ask
    allow: list[str] = Field(
        default_factory=lambda: [
            "git status",
            "git diff",
            "pytest",
            "eslint *",
        ]
    )
    block: list[str] = Field(
        default_factory=lambda: [
            "rm *",
            "curl *| sh",
            "*> /dev/*",
        ]
    )
    timeout_seconds: float = 30.0


class ContextSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/context/commands"


class IntegrationEndpointSettings(BaseModel):
    url: str
    triggers: list[str] = Field(default_factory=list)


class IntegrationsSettings(BaseModel):
    sourcegraph: IntegrationEndpointSettings = Field(
        default_factory=lambda: IntegrationEndpointSettings(
            url="https://sourcegraph.com",
            triggers=["@sourcegraph"],
        )
    )
    ghe: IntegrationEndpointSettings = Field(
        default_factory=lambda: IntegrationEndpointSettings(
            url="https://api.github.com",
            triggers=["@ghe"],
        )
    )
    gitlab: IntegrationEndpointSettings = Field(
        default_factory=lambda: IntegrationEndpointSettings(
            url="https://gitlab.com/api/v4",
            triggers=["@gitlab"],
        )
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DAARI_", env_nested_delimiter="__")

    server: ServerSettings = Field(default_factory=ServerSettings)
    models: ModelsSettings = Field(default_factory=ModelsSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    frontier: FrontierSettings = Field(default_factory=FrontierSettings)
    tools: ToolsSettings = Field(default_factory=ToolsSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    integrations: IntegrationsSettings = Field(default_factory=IntegrationsSettings)
    enterprise: OrgSettings = Field(default_factory=OrgSettings)
    skills_system_prefix: str = ""

    @classmethod
    def load(cls, config_path: Path | None = None) -> Settings:
        defaults = _load_defaults_yaml()
        file_data: dict[str, Any] = {}
        path = config_path or Path.home() / ".daari" / "config.yaml"
        if path.is_file():
            with path.open(encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                if isinstance(loaded, dict):
                    file_data = loaded
        profile_data = _load_profile_overrides()
        env_data = _load_env_overrides()
        merged = _deep_merge(_deep_merge(_deep_merge(defaults, file_data), profile_data), env_data)
        if isinstance(merged.get("org"), dict):
            merged["enterprise"] = _deep_merge(merged.get("enterprise", {}), merged["org"])
            merged.pop("org", None)
        merged["skills_system_prefix"] = _load_skills_system_prefix()
        return cls.model_validate(merged)

    @property
    def l0_cache_path(self) -> Path:
        return Path(self.cache.l0.path).expanduser()

    @property
    def l1_cache_path(self) -> Path:
        return Path(self.cache.l1.path).expanduser()

    @property
    def context_store_path(self) -> Path:
        return Path(self.context.path).expanduser()

    @property
    def org_cache_root(self) -> Path | None:
        org_id = self.enterprise.resolved_org_id
        if not self.enterprise.enabled or not org_id:
            return None
        if self.enterprise.shared_cache_path:
            return Path(self.enterprise.shared_cache_path).expanduser()
        return Path.home() / ".daari" / "org" / org_id / "cache"

    @property
    def org_shared_cache_root(self) -> Path | None:
        org_id = self.enterprise.resolved_org_id
        if not org_id:
            return None
        if self.enterprise.shared_cache_path:
            return Path(self.enterprise.shared_cache_path).expanduser()
        return Path.home() / ".daari" / "org" / org_id / "shared-cache"

    def resolve_frontier_api_key(self) -> str | None:
        return os.environ.get("DAARI_FRONTIER_API_KEY") or os.environ.get("OPENAI_API_KEY")


def _load_defaults_yaml() -> dict[str, Any]:
    path = Path(__file__).parent / "defaults.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_env_overrides() -> dict[str, Any]:
    """Load DAARI_* env vars into nested config dict using __ separator."""
    data: dict[str, Any] = {}
    prefix = "DAARI_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        if "__" not in key:
            continue
        path = key[len(prefix) :].lower().split("__")
        cursor: dict[str, Any] = data
        for segment in path[:-1]:
            if segment not in cursor or not isinstance(cursor[segment], dict):
                cursor[segment] = {}
            cursor = cursor[segment]
        cursor[path[-1]] = _coerce_env_value(value)
    org_id = os.environ.get("DAARI_ORG_ID")
    if org_id:
        enterprise = data.setdefault("enterprise", {})
        if isinstance(enterprise, dict):
            enterprise.setdefault("enabled", True)
            enterprise["org_id"] = org_id
    return data


def _load_profile_overrides() -> dict[str, Any]:
    profile_env = (os.environ.get("DAARI_PROFILE") or "").strip()
    profile_path = _resolve_profile_path(profile_env)
    if profile_path is None or not profile_path.is_file():
        return {}
    with profile_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def _resolve_profile_path(profile_env: str) -> Path | None:
    profile_root = Path.home() / ".daari" / "profiles"
    if profile_env:
        env_path = Path(profile_env).expanduser()
        if env_path.is_absolute() or "/" in profile_env:
            return env_path
        if env_path.suffix in {".yaml", ".yml"}:
            return profile_root / env_path
        return profile_root / f"{profile_env}.yaml"

    cwd = Path.cwd().resolve()
    cwd_hash = hashlib.sha1(str(cwd).encode("utf-8")).hexdigest()[:12]
    cwd_slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", cwd.name).strip("-").lower() or "project"
    hash_candidate = profile_root / f"{cwd_hash}.yaml"
    slug_candidate = profile_root / f"{cwd_slug}.yaml"
    if hash_candidate.is_file():
        return hash_candidate
    if slug_candidate.is_file():
        return slug_candidate
    return None


def _load_skills_system_prefix() -> str:
    skills_dir = Path.home() / ".daari" / "skills"
    if not skills_dir.is_dir():
        return ""
    sections: list[str] = []
    for path in sorted(skills_dir.glob("*.md")):
        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not content:
            continue
        sections.append(f"## Skill: {path.stem}\n{content}")
    if not sections:
        return ""
    return "# Local daari skills\n\n" + "\n\n".join(sections)


def _coerce_env_value(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


@lru_cache
def get_settings() -> Settings:
    return Settings.load()

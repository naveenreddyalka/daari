from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
        env_data = _load_env_overrides()
        merged = _deep_merge(_deep_merge(defaults, file_data), env_data)
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
        path = key[len(prefix) :].lower().split("__")
        cursor: dict[str, Any] = data
        for segment in path[:-1]:
            if segment not in cursor or not isinstance(cursor[segment], dict):
                cursor[segment] = {}
            cursor = cursor[segment]
        cursor[path[-1]] = _coerce_env_value(value)
    return data


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

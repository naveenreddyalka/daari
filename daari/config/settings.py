from __future__ import annotations

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


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"


class L0CacheSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/cache/l0"


class CacheSettings(BaseModel):
    l0: L0CacheSettings = Field(default_factory=L0CacheSettings)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DAARI_", env_nested_delimiter="__")

    server: ServerSettings = Field(default_factory=ServerSettings)
    models: ModelsSettings = Field(default_factory=ModelsSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)

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
        merged = _deep_merge(defaults, file_data)
        return cls.model_validate(merged)

    @property
    def l0_cache_path(self) -> Path:
        return Path(self.cache.l0.path).expanduser()


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


@lru_cache
def get_settings() -> Settings:
    return Settings.load()

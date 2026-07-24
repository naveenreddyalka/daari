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
    # When set, all endpoints except health checks require this key via
    # Authorization: Bearer or x-api-key (issue #86 — tunnel exposure).
    api_key: str = ""


class ModelsSettings(BaseModel):
    l3: str = "llama3.2:3b"
    l4: str = "llama3.1:8b"
    l5: str = "llama3.1:70b"
    weights: dict[str, dict[str, float]] = Field(default_factory=dict)


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"


class MLXSettings(BaseModel):
    """Optional MLX backend (issue #97): serve tiers via mlx_lm.server."""

    enabled: bool = False
    base_url: str = "http://127.0.0.1:11440"
    # Tier -> model name, e.g. {"L3": "mlx-community/Llama-3.2-3B-Instruct-4bit"}.
    # Tiers not listed here stay on Ollama.
    models: dict[str, str] = Field(default_factory=dict)


class L0CacheSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/cache/l0"
    # 0 = never expire (default, preserves prior behavior).
    ttl_seconds: float = 0.0


class L1CacheSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/cache/l1"
    similarity_threshold: float = 0.88
    # Near-miss band [draft_threshold, similarity_threshold): the prior answer
    # is injected as a draft for the serving model instead of being discarded.
    draft_threshold: float = 0.75
    max_entries: int = 1000
    embedding_model: str = "nomic-embed-text"
    # 0 = never expire (default, preserves prior behavior).
    ttl_seconds: float = 0.0
    # In-memory LRU for embeddings; 0 disables memoization.
    embed_cache_size: int = 512
    # Normalize template/boilerplate text before embedding (Trust PRD T1a).
    normalize_inputs: bool = True
    # Fraction of L1 hits verified in the background against a fresh local
    # answer (Trust PRD T1c). 0 disables shadow sampling.
    shadow_sample_rate: float = 0.05


class CacheSettings(BaseModel):
    l0: L0CacheSettings = Field(default_factory=L0CacheSettings)
    l1: L1CacheSettings = Field(default_factory=L1CacheSettings)


class FrontierProviderConfig(BaseModel):
    """One L6 provider in the fallback chain (issue #109)."""

    id: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    # Explicit keys (rarely set in YAML — prefer api_key_env). Rotated by weight.
    keys: list[str] = Field(default_factory=list)
    api_key_env: str = ""
    weight: float = 1.0
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0


class FrontierSettings(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    confidence_threshold: float = 0.7
    base_url: str = "https://api.openai.com/v1"
    # Ordered failover list (issue #109). Empty → use the scalar
    # provider/base_url/model + resolve_frontier_api_key() shorthand.
    providers: list[FrontierProviderConfig] = Field(default_factory=list)
    # 0 = unlimited. When today's estimated spend reaches the cap, daari stops
    # escalating to L6 and serves the best local answer instead.
    daily_budget_usd: float = 0.0
    # 0 = unlimited. Same hard-cap behavior over the calendar month (T5a).
    monthly_budget_usd: float = 0.0
    # Crossing this fraction of any budget still serves L6 but attaches
    # daari_meta.warning = "frontier_budget_warning" (T5a).
    soft_budget_ratio: float = 0.8
    # Regex-scrub emails/phones/SSNs/cards/IPs from the outbound L6 copy
    # only; local processing sees the original text (T5c).
    scrub_pii: bool = False
    price_per_1k_tokens: float = 0.002
    # Strip daari-internal system hints, collapse duplicate system prompts,
    # and trim history before escalating to L6 (frontier tokens cost money).
    slim_prompts: bool = True
    max_history_messages: int = 8
    # Mark the stable system prefix for provider-side prompt caching
    # (Anthropic cache_control; OpenAI caches automatically). Trust PRD T2a.
    prompt_cache: bool = True
    # Relevance-prune long context before L6 (Trust PRD T2c). Opt-in.
    compress_context: bool = False
    compress_target_ratio: float = 0.6


class CategoryPolicy(BaseModel):
    tier: str | None = None  # L3 | L4 | L5; None keeps weight-based choice
    cache: str = "default"  # default | skip
    # Per-category cache max age in seconds (e.g. shorter for doc_qa).
    # None inherits the global cache.l0/l1 ttl_seconds.
    ttl_seconds: float | None = None
    # Per-category latency budget in ms (Trust PRD T3b). None inherits
    # routing.latency_budget_ms.
    latency_budget_ms: int | None = None


class RoutingSettings(BaseModel):
    prefer: str = "balanced"  # latency | accuracy | balanced
    confidence_threshold: float = 0.7
    category_policies: dict[str, CategoryPolicy] = Field(default_factory=dict)
    # Cap the local tier chosen for chat/Ask requests (L3|L4|L5). None keeps
    # the weight/length heuristics unbounded. X-Daari-Tier-Cap header wins.
    max_tier_for_chat: str | None = None
    # Global latency budget in ms enforced against `daari profile` data
    # (Trust PRD T3b). 0 disables. X-Daari-Latency-Budget header wins.
    latency_budget_ms: int = 0
    # Prefer already-loaded Ollama models on weight ties (Trust PRD T3c).
    warm_model_preference: bool = True
    # Use the trained personal classifier (`daari learn train-router`) to
    # override heuristic categorization when confident (Trust PRD Train 4).
    learned_router: bool = False


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


class UsageSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/usage/ledger.sqlite3"
    # Frontier rate used to estimate what locally-served tokens would have cost.
    frontier_price_per_1k_tokens: float = 0.002


class TraceSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/traces/traces.sqlite3"
    max_entries: int = 200


class ObservabilitySettings(BaseModel):
    # Gateway request log rotation; 0 max bytes disables rotation.
    request_log_max_bytes: int = 5 * 1024 * 1024
    request_log_backups: int = 3


class LearningSettings(BaseModel):
    """Phase D: on-device outcome capture — metadata only, never prompt text."""

    enabled: bool = True
    path: str = "~/.daari/feedback/feedback.sqlite3"
    max_rows: int = 20000
    # D1c routing tuner: derive per-category confidence thresholds from
    # outcomes. Off by default — behavior is identical to the global
    # routing.confidence_threshold until explicitly enabled.
    auto_tune: bool = False
    tuner_min_samples: int = 50
    # D2a: opt-in capture of (prompt, completion) training examples. Unlike
    # the outcome store this keeps full text, so it is off by default.
    capture_examples: bool = False
    examples_path: str = "~/.daari/training/examples.sqlite3"
    examples_max_rows: int = 5000
    # Learned router (Trust PRD Train 4): never predict from fewer samples.
    router_min_samples: int = 200
    router_model_path: str = "~/.daari/learning/router-model.json"
    # D3: opt-in collective stats. Export is always local + reviewable;
    # upload requires BOTH the flag and a URL, and sends metadata only
    # (tier/category aggregates, latency, model IDs — never prompt text).
    collective_enabled: bool = False
    collective_url: str = ""
    collective_token: str = ""


class ContextOptimizerSettings(BaseModel):
    enabled: bool = True
    max_history_messages: int = 20
    squeeze_whitespace: bool = True
    # Summarize over-limit history into a pinned recap instead of dropping
    # it (Trust PRD T2b). Opt-in.
    compact: bool = False


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
    mlx: MLXSettings = Field(default_factory=MLXSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    frontier: FrontierSettings = Field(default_factory=FrontierSettings)
    tools: ToolsSettings = Field(default_factory=ToolsSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    usage: UsageSettings = Field(default_factory=UsageSettings)
    trace: TraceSettings = Field(default_factory=TraceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    learning: LearningSettings = Field(default_factory=LearningSettings)
    context_optimizer: ContextOptimizerSettings = Field(default_factory=ContextOptimizerSettings)
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
    def usage_ledger_path(self) -> Path:
        return Path(self.usage.path).expanduser()

    @property
    def trace_store_path(self) -> Path:
        return Path(self.trace.path).expanduser()

    @property
    def feedback_store_path(self) -> Path:
        return Path(self.learning.path).expanduser()

    @property
    def example_store_path(self) -> Path:
        return Path(self.learning.examples_path).expanduser()

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

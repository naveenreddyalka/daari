from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from daari.enterprise.config import OrgSettings


class RuntimeSettings(BaseModel):
    """Settings mutated after load — reject bad setattr immediately (#152)."""

    model_config = ConfigDict(validate_assignment=True)


class VirtualKeysSettings(BaseModel):
    """Per-key budgets / RPM / tier caps (issue #111). Off until a key is created."""

    enabled: bool = True
    path: str = "~/.daari/auth/virtual-keys.sqlite3"


class RateLimitSettings(BaseModel):
    """Global request / token / concurrency caps (issue #169). 0 = unlimited."""

    rpm: int = Field(default=0, description="Default requests per minute per key (0=unlimited).")
    tpm: int = Field(default=0, description="Default tokens per minute per key (0=unlimited).")
    model_rpm: int = Field(
        default=0,
        description="Per-key-per-model RPM. 0 falls back to rpm.",
    )
    model_tpm: int = Field(
        default=0,
        description="Per-key-per-model TPM. 0 falls back to tpm.",
    )
    max_in_flight: int = Field(
        default=0,
        description="Global in-flight request cap. 0 disables the concurrency gate.",
    )
    queue_size: int = Field(
        default=32,
        description="Waiters allowed when in-flight is full; overflow is 503 + Retry-After.",
    )
    retry_after_seconds: int = Field(default=1, description="Retry-After value on 429/503.")


class ServerSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 11435
    # When set, all endpoints except health checks require this key via
    # Authorization: Bearer or x-api-key (issue #86 — tunnel exposure).
    # Virtual keys (issue #111) are accepted alongside this master key.
    api_key: str = ""
    virtual_keys: VirtualKeysSettings = Field(default_factory=VirtualKeysSettings)
    sse_keepalive_seconds: float = Field(
        default=10.0,
        ge=0.0,
        description=(
            "Idle seconds before a streaming response emits a keepalive frame "
            "(SSE comment `: keepalive` on OpenAI/Anthropic/Responses routes, a "
            "blank line on the NDJSON Ollama facade). Keeps proxies and SDK read "
            "timeouts from dropping slow-to-first-token streams. 0 disables."
        ),
    )


class ModelsSettings(BaseModel):
    l3: str = "llama3.2:3b"
    l4: str = "llama3.1:8b"
    l5: str = "llama3.1:70b"
    weights: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Per-model capability tags (tools/json/vision/long_context). Empty →
    # stock defaults in CapabilityCatalog (issue #113).
    capabilities: dict[str, list[str]] = Field(default_factory=dict)


class OllamaSettings(BaseModel):
    base_url: str = "http://127.0.0.1:11434"


class MLXSettings(BaseModel):
    """Optional MLX backend (issue #97): serve tiers via mlx_lm.server."""

    enabled: bool = False
    base_url: str = "http://127.0.0.1:11440"
    # Tier -> model name, e.g. {"L3": "mlx-community/Llama-3.2-3B-Instruct-4bit"}.
    # Tiers not listed here stay on Ollama.
    models: dict[str, str] = Field(default_factory=dict)


class L0CacheSettings(RuntimeSettings):
    enabled: bool = True
    path: str = "~/.daari/cache/l0"
    # 0 = never expire (default, preserves prior behavior).
    ttl_seconds: float = Field(default=0.0, ge=0.0)


class L1CacheSettings(RuntimeSettings):
    enabled: bool = True
    path: str = "~/.daari/cache/l1"
    similarity_threshold: float = Field(default=0.88, ge=0.0, le=1.0)
    # Near-miss band [draft_threshold, similarity_threshold): the prior answer
    # is injected as a draft for the serving model instead of being discarded.
    draft_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    max_entries: int = 1000
    embedding_model: str = "nomic-embed-text"
    # 0 = never expire (default, preserves prior behavior).
    ttl_seconds: float = Field(default=0.0, ge=0.0)
    # In-memory LRU for embeddings; 0 disables memoization.
    embed_cache_size: int = 512
    # Normalize template/boilerplate text before embedding (Trust PRD T1a).
    normalize_inputs: bool = True
    verify: Literal["none", "lexical", "model"] = Field(
        default="lexical",
        description=(
            "Second-stage check before serving a semantic hit, because a cosine "
            "threshold alone cannot separate a paraphrase from a near-miss. "
            "`none` serves any hit above the threshold; `lexical` (default) vetoes "
            "hits whose numbers, units, or negation differ; `model` additionally "
            "asks a local model to confirm equivalence."
        ),
    )
    # Fraction of L1 hits verified in the background against a fresh local
    # answer (Trust PRD T1c). 0 disables shadow sampling.
    shadow_sample_rate: float = Field(default=0.05, ge=0.0, le=1.0)


class CacheSettings(RuntimeSettings):
    l0: L0CacheSettings = Field(default_factory=L0CacheSettings)
    l1: L1CacheSettings = Field(default_factory=L1CacheSettings)
    # F4: disk (default) or redis for shared L0/L1 across replicas (#112, #135).
    backend: Literal["disk", "redis"] = "disk"
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_prefix: str = "daari:l0:"
    redis_l1_prefix: str = "daari:l1:"


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
    # Zero-data-retention. Required when the client sends `provider.zdr`.
    zdr: bool = False


class FrontierSettings(RuntimeSettings):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-4o-mini"
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    base_url: str = "https://api.openai.com/v1"
    # Ordered failover list (issue #109). Empty → use the scalar
    # provider/base_url/model + resolve_frontier_api_key() shorthand.
    providers: list[FrontierProviderConfig] = Field(default_factory=list)
    # 0 = unlimited. When today's estimated spend reaches the cap, daari stops
    # escalating to L6 and serves the best local answer instead.
    daily_budget_usd: float = Field(default=0.0, ge=0.0)
    # 0 = unlimited. Same hard-cap behavior over the calendar month (T5a).
    monthly_budget_usd: float = Field(default=0.0, ge=0.0)
    # Crossing this fraction of any budget still serves L6 but attaches
    # daari_meta.warning = "frontier_budget_warning" (T5a).
    soft_budget_ratio: float = Field(default=0.8, ge=0.0, le=1.0)
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


class OrgPoolSettings(BaseModel):
    """Shared org GPU inference pool between local L5 and frontier L6 (issue #118)."""

    enabled: bool = False
    base_url: str = ""
    model: str = ""
    # Tier label recorded in daari_meta (L5.5 conceptually; stored as L5-org).
    tier: str = "L5-org"


class LocalBackendSettings(BaseModel):
    """One local inference host in the per-tier pool (issue #170)."""

    id: str = ""
    base_url: str = ""
    kind: str = "ollama"
    model: str = ""
    tiers: list[str] = Field(default_factory=lambda: ["L3", "L4", "L5"])
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0


class LocalPoolSettings(BaseModel):
    """Health-checked local backend pool (issue #170). Empty backends → ollama.base_url."""

    strategy: str = Field(
        default="least_outstanding",
        description="Host pick: least_outstanding or round_robin. Warm models still win ties.",
    )
    health_interval_seconds: float = Field(
        default=15.0,
        description="Background health-check interval. Requests use the last snapshot.",
    )
    backends: list[LocalBackendSettings] = Field(default_factory=list)


class RoutingSettings(RuntimeSettings):
    prefer: Literal["latency", "accuracy", "balanced", "cost"] = "balanced"
    confidence_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    category_policies: dict[str, CategoryPolicy] = Field(default_factory=dict)
    # Cap the local tier chosen for chat/Ask requests (L3|L4|L5). None keeps
    # the weight/length heuristics unbounded. X-Daari-Tier-Cap header wins.
    max_tier_for_chat: Literal["L3", "L4", "L5"] | None = None
    # Global latency budget in ms enforced against `daari profile` data
    # (Trust PRD T3b). 0 disables. X-Daari-Latency-Budget header wins.
    latency_budget_ms: int = Field(default=0, ge=0)
    # Prefer already-loaded Ollama models on weight ties (Trust PRD T3c).
    warm_model_preference: bool = True
    # Use the trained personal classifier (`daari learn train-router`) to
    # override heuristic categorization when confident (Trust PRD Train 4).
    learned_router: bool = False
    # Org inference pool (device-local → org pool → frontier).
    org_pool: OrgPoolSettings = Field(default_factory=OrgPoolSettings)
    local_pool: LocalPoolSettings = Field(default_factory=LocalPoolSettings)


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


class UpstreamRetrySettings(BaseModel):
    attempts: int = Field(
        default=3,
        description=(
            "Total attempts per upstream call, counting the first. `1` disables "
            "retries. Only transient failures are retried (408, 429, 5xx, connect "
            "and read timeouts); a 401 or malformed body fails immediately."
        ),
    )
    base_delay_ms: int = Field(
        default=200,
        description="First backoff, doubled per retry up to `max_delay_ms`.",
    )
    max_delay_ms: int = Field(
        default=5_000, description="Ceiling for a single backoff interval."
    )
    jitter: float = Field(
        default=0.5,
        description=(
            "Fraction of each backoff that is randomized, keeping the delay in "
            "[d*(1-jitter), d]. Spreads retries from requests that failed "
            "together instead of returning them in lockstep."
        ),
    )


class UpstreamSettings(BaseModel):
    """Timeouts and retries for calls daari makes to model backends (#159)."""

    local_timeout_seconds: float = Field(
        default=120.0,
        description=(
            "Request timeout for local backends (Ollama, MLX). Generous because a "
            "large local model on a cold start can be genuinely slow."
        ),
    )
    frontier_timeout_seconds: float = Field(
        default=90.0,
        description=(
            "Request timeout for frontier (L6) providers. Lower than local, since "
            "a hosted API that has not answered in 90s is usually not going to."
        ),
    )
    retry: UpstreamRetrySettings = Field(default_factory=UpstreamRetrySettings)


class ModelPrice(BaseModel):
    """USD per 1M tokens, which is how providers quote list prices."""

    input_per_1m: float
    output_per_1m: float
    # Providers discount cached prompt prefixes; None means bill at input rate.
    cached_input_per_1m: float | None = None


# List prices captured 2026-08-11. These move, so treat the table as a
# convenience default: anything in `pricing.models` overrides an entry here,
# and unpriced models fall back to frontier.price_per_1k_tokens.
_DEFAULT_MODEL_PRICES: dict[str, dict[str, float]] = {
    "gpt-4o": {"input_per_1m": 2.50, "output_per_1m": 10.00, "cached_input_per_1m": 1.25},
    "gpt-4o-mini": {"input_per_1m": 0.15, "output_per_1m": 0.60, "cached_input_per_1m": 0.075},
    "claude-3-5-sonnet": {"input_per_1m": 3.00, "output_per_1m": 15.00},
    "claude-3-5-haiku": {"input_per_1m": 0.80, "output_per_1m": 4.00},
    "claude-3-opus": {"input_per_1m": 15.00, "output_per_1m": 75.00},
}


class PricingSettings(BaseModel):
    models: dict[str, ModelPrice] = Field(
        default_factory=lambda: {
            name: ModelPrice(**price) for name, price in _DEFAULT_MODEL_PRICES.items()
        },
        description=(
            "Per-model, per-direction USD rates per 1M tokens. Keys match on "
            "longest prefix, so `gpt-4o` also prices `gpt-4o-2024-08-06`. Models "
            "absent here fall back to `usage.frontier_price_per_1k_tokens`; run "
            "`daari doctor` to list models being billed at the fallback rate."
        ),
    )


class UsageSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/usage/ledger.sqlite3"
    frontier_price_per_1k_tokens: float = Field(
        default=0.002,
        description=(
            "Flat fallback rate used to estimate what locally-served tokens would "
            "have cost on a frontier model. Applies only to models absent from "
            "`pricing.models`, and ignores input/output direction."
        ),
    )


class TraceSettings(BaseModel):
    enabled: bool = True
    path: str = "~/.daari/traces/traces.sqlite3"
    max_entries: int = 200


class ObservabilitySettings(RuntimeSettings):
    # Gateway request log rotation; 0 max bytes disables rotation.
    request_log_max_bytes: int = Field(default=5 * 1024 * 1024, ge=0)
    request_log_backups: int = Field(default=3, ge=0)
    # F3: expose GET /metrics in Prometheus exposition format. Open when
    # server.api_key is unset; honors auth otherwise (issue #107).
    prometheus: bool = True
    # Optional OTel export of RequestTrace steps (issue #115). Requires
    # opentelemetry-api; no-op when the package is missing.
    otel: bool = False
    # Allow authenticated PATCH of a safe config subset via the web UI.
    config_editor: bool = False
    # sqlite (default) or postgres for ledger + traces (issue #116).
    backend: Literal["sqlite", "postgres"] = "sqlite"
    postgres_url: str = ""
    # Emit gateway request logs as single-line JSON to stdout (containers).
    structured_json_logs: bool = False
    # Hint that redis+postgres backends are in use (no local request state).
    stateless: bool = False


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


class GuardrailRuleSettings(BaseModel):
    name: str = "rule"
    pattern: str | None = None
    action: str = "block"  # block | warn | redact
    kind: str = "deny"  # deny | allow | secret | pii


class GuardrailSettings(BaseModel):
    """Input/output checks before and after model tiers (issue #110). Off by default."""

    enabled: bool = False
    max_prompt_chars: int = 0  # 0 = unlimited
    injection_action: str = "block"
    block_message: str = "Request blocked by daari guardrail."
    input_rules: list[GuardrailRuleSettings] = Field(default_factory=list)
    output_rules: list[GuardrailRuleSettings] = Field(default_factory=list)


class BoundariesSettings(RuntimeSettings):
    """Product-domain scope gate (Roadmap F6). Off by default.

    When enabled, clearly out-of-scope prompts are refused locally before any
    model spend. Ambiguous prompts may use a cheap local judge (B1).
    """

    enabled: bool = False
    mode: Literal["off", "warn", "block"] = "block"
    product_name: str = ""
    product_description: str = ""
    allow_topics: list[str] = Field(default_factory=list)
    deny_topics: list[str] = Field(default_factory=list)
    examples_in: list[str] = Field(default_factory=list)
    examples_out: list[str] = Field(default_factory=list)
    refuse_message: str = "This assistant can only help with in-product questions."
    clear_out_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    clear_in_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    local_judge_model: str | None = None
    quorum_votes: int = 2
    frontier_judge_daily_budget_usd: float = 0.5
    stages_b0: bool = True
    stages_b1: bool = True
    stages_b2: bool = True
    stages_b3: bool = False
    active_profile: str = ""
    profiles: dict[str, dict] = Field(default_factory=dict)


class IntegrationEndpointSettings(BaseModel):
    url: str
    triggers: list[str] = Field(default_factory=list)


class McpServerSettings(BaseModel):
    """External MCP server daari can call as a tool (issue #121)."""

    id: str
    url: str
    token: str = ""
    triggers: list[str] = Field(default_factory=list)


class McpToolPolicySettings(BaseModel):
    """Glob-style MCP tool allow/deny lists (issue #277). Deny wins; empty allow = all."""

    allow: list[str] = Field(
        default_factory=list,
        description="MCP tool names (glob) the caller may call. Empty = every tool not denied.",
    )
    deny: list[str] = Field(
        default_factory=list,
        description="MCP tool names (glob) the caller may never call. Deny beats allow.",
    )


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
    # F5 MCP egress: daari → external MCP servers.
    mcp_servers: list[McpServerSettings] = Field(default_factory=list)
    # MCP ingress tool governance: global default, then per-team (by team name);
    # a virtual key's `metadata.mcp` layers on top (issue #277).
    mcp_policy: McpToolPolicySettings = Field(
        default_factory=McpToolPolicySettings,
        description="Default MCP tool policy for every caller, including the master key.",
    )
    mcp_team_policies: dict[str, McpToolPolicySettings] = Field(
        default_factory=dict,
        description="Per-team MCP tool policy keyed by team name; layered on mcp_policy.",
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DAARI_", env_nested_delimiter="__")

    server: ServerSettings = Field(default_factory=ServerSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    models: ModelsSettings = Field(default_factory=ModelsSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    mlx: MLXSettings = Field(default_factory=MLXSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    frontier: FrontierSettings = Field(default_factory=FrontierSettings)
    tools: ToolsSettings = Field(default_factory=ToolsSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    usage: UsageSettings = Field(default_factory=UsageSettings)
    pricing: PricingSettings = Field(default_factory=PricingSettings)
    upstream: UpstreamSettings = Field(default_factory=UpstreamSettings)
    trace: TraceSettings = Field(default_factory=TraceSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    learning: LearningSettings = Field(default_factory=LearningSettings)
    context_optimizer: ContextOptimizerSettings = Field(default_factory=ContextOptimizerSettings)
    guardrails: GuardrailSettings = Field(default_factory=GuardrailSettings)
    boundaries: BoundariesSettings = Field(default_factory=BoundariesSettings)
    integrations: IntegrationsSettings = Field(default_factory=IntegrationsSettings)
    enterprise: OrgSettings = Field(default_factory=OrgSettings)
    skills_system_prefix: str = ""

    @classmethod
    def load(cls, config_path: Path | None = None, *, resolve_secrets: bool = True) -> Settings:
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
        settings = cls.model_validate(merged)
        if resolve_secrets:
            from daari.security.secret_refs import resolve_tree

            return cls.model_validate(resolve_tree(settings.model_dump()))
        return settings

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
    def virtual_keys_path(self) -> Path:
        return Path(self.server.virtual_keys.path).expanduser()

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
        return (
            os.environ.get("DAARI_FRONTIER_API_KEY")
            or os.environ.get("OPENROUTER_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )


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

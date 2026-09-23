from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from daari.gateway.provider_prefs import ProviderPreferences
from daari.gateway.sampling import SamplingParams


class ContentImage(BaseModel):
    """One image the client sent. `data` is raw base64; `url` may be a data: or https URL."""

    media_type: str = "image/png"
    data: str | None = None
    url: str | None = None

    def as_base64(self) -> str | None:
        if self.data:
            return self.data
        if self.url and self.url.startswith("data:") and "," in self.url:
            return self.url.split(",", 1)[1]
        return None

    def as_data_url(self) -> str | None:
        if self.url:
            return self.url
        if self.data:
            return f"data:{self.media_type};base64,{self.data}"
        return None

    def cache_token(self) -> str:
        import hashlib

        raw = self.as_base64() or self.url or ""
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


class ContentAudio(BaseModel):
    """One OpenAI ``input_audio`` part. ``data`` is raw base64; ``format`` is wav/mp3."""

    data: str
    format: str = "wav"

    def cache_token(self) -> str:
        import hashlib

        raw = f"{self.format}:{self.data}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def as_openai_part(self) -> dict[str, Any]:
        return {
            "type": "input_audio",
            "input_audio": {"data": self.data, "format": self.format},
        }


class Message(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[Any] | None = None
    images: list[ContentImage] = Field(default_factory=list)
    # OpenAI input_audio parts (#981). Empty by default so cache keys stay stable.
    audio: list[ContentAudio] = Field(default_factory=list)
    # Anthropic tool_result blocks carry tool_use_id; OpenAI uses this as
    # tool_call_id. Absent on ordinary turns so cache keys stay stable.
    tool_call_id: str | None = None
    # Signed thinking / redacted_thinking blocks for Anthropic L6 replay (#431).
    # Empty by default so cache keys stay stable when absent.
    thinking_blocks: list[dict[str, Any]] = Field(default_factory=list)
    # Anthropic prompt-cache marker (system / tool blocks). Preserved on L6
    # Messages egress so ttl 5m vs 1h reaches the provider (#434).
    cache_control: dict[str, Any] | None = None


class RequestMeta(BaseModel):
    no_cache: bool = False
    tier_override: str | None = None
    tier_cap: str | None = None
    # Max acceptable local-model latency in ms (X-Daari-Latency-Budget).
    latency_budget_ms: int | None = None
    # Wall-clock budget for the whole escalation chain (X-Daari-Deadline-Ms).
    # None means the request has no header deadline; the setting may still apply.
    deadline_ms: int | None = None
    client_id: str | None = None
    # Raw User-Agent (gateway sniff). Used for classify_user_turn agent shortcut.
    user_agent: str | None = None
    # OpenAI `user` or an explicit session id. Used only when session affinity
    # is on; absent values leave cache keys unchanged.
    user: str | None = None
    session_id: str | None = None
    # Set when a continuation replayed a pin. Not part of the cache key.
    session_pinned_tier: str | None = None
    no_frontier: bool = False
    confirm_tool: bool = False
    rerun_command: bool = False
    stream_include_usage: bool = False
    # Named boundaries.profiles overlay (X-Daari-Boundary-Profile / #171).
    boundary_profile: str | None = None
    # L6 residency pin from virtual key / team (#466).
    region_pin: str | None = None
    # Expanded model allowlist (#708). None = that side does not restrict.
    key_model_patterns: list[str] | None = None
    team_model_patterns: list[str] | None = None
    # Chargeback attribution (#709). Folded into cache keys only when
    # cache_scope is team or key (#768); global leaves hashes unchanged.
    key_id: str | None = None
    team_id: str | None = None
    # Effective isolation: global (default) | team | key. Set from the virtual
    # key and team; unauthenticated requests stay global.
    cache_scope: str = "global"
    # Client anthropic-beta / anthropic-version forwarded on the L6 Anthropic leg (#455).
    anthropic_beta: str | None = None
    anthropic_version: str | None = None
    # Sanitized X-Request-ID (or generated) for spend/log correlation (#965).
    request_id: str | None = None


class InternalRequest(BaseModel):
    messages: list[Message]
    model: str
    temperature: float = 0.7
    tools: list[Any] | None = None
    stream: bool = False
    # Generation controls the client asked for; previously dropped (#161).
    sampling: SamplingParams = Field(default_factory=SamplingParams)
    meta: RequestMeta = Field(default_factory=RequestMeta)
    # OpenRouter-shaped routing constraints (G2 / #224). None when omitted.
    provider: ProviderPreferences | None = None

    @property
    def has_tool_calls_in_history(self) -> bool:
        for message in self.messages:
            if message.tool_calls:
                return True
        return False


class DaariMeta(BaseModel):
    tier: str
    cache_hit: bool = False
    # An L1 near-miss was injected as a draft to steer generation (#21);
    # surfaced as `x-daari-cache: draft` (#278).
    draft: bool = False
    executor: str
    provider_id: str | None = None
    # L6 slot region label when a frontier provider served the request (#466).
    region: str | None = None
    tool: str | None = None
    latency_ms: int = 0
    model: str | None = None
    task_type: str | None = None
    complexity: str | None = None
    trace_id: str | None = None
    confidence: float | None = None
    # Chars actually sent to the provider when it differs from the client
    # request (e.g. frontier prompt slimming); used for ledger accounting.
    prompt_chars: int | None = None
    # Token counts as reported by the provider. usage_estimated stays True when
    # they had to be derived from character length instead (#156).
    input_tokens: int | None = None
    output_tokens: int | None = None
    usage_estimated: bool = True
    escalated_from: str | None = None
    rule_id: str | None = None
    warning: str | None = None
    # Client params the serving tier could not honor (#1013).
    dropped_params: list[str] | None = None
    policy: str | None = None
    pending_command: str | None = None
    confirmation_prompt: str | None = None
    confirmation_header: str | None = None
    # Product boundary decision (F6): {label, stage, confidence, reason, mode}
    boundary: dict | None = None
    # Local pool host that served the request (issue #170).
    backend_id: str | None = None
    # G2: OpenRouter usage.cost, cached prompt tokens, and the client
    # `provider` constraint that was honored or refused.
    cost_usd: float | None = None
    cached_tokens: int | None = None
    provider_prefs: dict | None = None
    # G3: local path is always $0; L6 rows keep upstream cost in cost_usd.
    daari_cost_usd: float | None = None
    # Client reasoning_effort when present (#297).
    reasoning_effort: str | None = None
    # Client service_tier when present (#430).
    service_tier: str | None = None
    # True when tools / tool history make this an agent turn (ADR-0004 / #604).
    agent_turn: bool | None = None


class InternalResponse(BaseModel):
    content: str
    model: str
    daari_meta: DaariMeta
    finish_reason: str = "stop"
    tool_calls: list[Any] | None = None

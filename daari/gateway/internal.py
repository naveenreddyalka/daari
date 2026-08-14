from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

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


class Message(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[Any] | None = None
    images: list[ContentImage] = Field(default_factory=list)
    # Anthropic tool_result blocks carry tool_use_id; OpenAI uses this as
    # tool_call_id. Absent on ordinary turns so cache keys stay stable.
    tool_call_id: str | None = None


class RequestMeta(BaseModel):
    no_cache: bool = False
    tier_override: str | None = None
    tier_cap: str | None = None
    # Max acceptable local-model latency in ms (X-Daari-Latency-Budget).
    latency_budget_ms: int | None = None
    client_id: str | None = None
    no_frontier: bool = False
    confirm_tool: bool = False
    rerun_command: bool = False
    stream_include_usage: bool = False


class InternalRequest(BaseModel):
    messages: list[Message]
    model: str
    temperature: float = 0.7
    tools: list[Any] | None = None
    stream: bool = False
    # Generation controls the client asked for; previously dropped (#161).
    sampling: SamplingParams = Field(default_factory=SamplingParams)
    meta: RequestMeta = Field(default_factory=RequestMeta)

    @property
    def has_tool_calls_in_history(self) -> bool:
        for message in self.messages:
            if message.tool_calls:
                return True
        return False


class DaariMeta(BaseModel):
    tier: str
    cache_hit: bool = False
    executor: str
    provider_id: str | None = None
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
    policy: str | None = None
    pending_command: str | None = None
    confirmation_prompt: str | None = None
    confirmation_header: str | None = None
    # Product boundary decision (F6): {label, stage, confidence, reason, mode}
    boundary: dict | None = None
    # Local pool host that served the request (issue #170).
    backend_id: str | None = None


class InternalResponse(BaseModel):
    content: str
    model: str
    daari_meta: DaariMeta
    finish_reason: str = "stop"
    tool_calls: list[Any] | None = None

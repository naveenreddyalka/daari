from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[Any] | None = None


class RequestMeta(BaseModel):
    no_cache: bool = False
    tier_override: str | None = None
    client_id: str | None = None
    no_frontier: bool = False
    confirm_tool: bool = False
    rerun_command: bool = False


class InternalRequest(BaseModel):
    messages: list[Message]
    model: str
    temperature: float = 0.7
    tools: list[Any] | None = None
    stream: bool = False
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
    confidence: float | None = None
    escalated_from: str | None = None
    rule_id: str | None = None
    warning: str | None = None
    policy: str | None = None
    pending_command: str | None = None
    confirmation_prompt: str | None = None
    confirmation_header: str | None = None


class InternalResponse(BaseModel):
    content: str
    model: str
    daari_meta: DaariMeta
    finish_reason: str = "stop"

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.router.router import AppContext


class ChatMessage(BaseModel):
    role: str
    content: str | None = None
    tool_calls: list[Any] | None = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    tools: list[Any] | None = None
    stream: bool = False


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    daari_meta: dict[str, Any] = Field(default_factory=dict)


def create_gateway_router() -> APIRouter:
    router = APIRouter()

    @router.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatCompletionRequest,
        request: Request,
        x_daari_no_cache: str | None = Header(default=None, alias="X-Daari-No-Cache"),
        x_daari_tier_override: str | None = Header(default=None, alias="X-Daari-Tier-Override"),
    ) -> dict[str, Any]:
        if body.stream:
            raise HTTPException(status_code=501, detail="Streaming not supported in Phase A")

        ctx: AppContext = request.app.state.ctx
        internal = InternalRequest(
            messages=[Message.model_validate(m.model_dump()) for m in body.messages],
            model=body.model or ctx.settings.models.l3,
            temperature=body.temperature,
            tools=body.tools,
            stream=body.stream,
            meta=RequestMeta(
                no_cache=x_daari_no_cache == "true",
                tier_override=x_daari_tier_override,
            ),
        )

        try:
            result = await ctx.router.route(internal)
        except Exception as exc:
            ctx.metrics.record_error()
            raise HTTPException(status_code=503, detail=f"Routing failed: {exc}") from exc

        return ChatCompletionResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            created=int(time.time()),
            model=result.model,
            choices=[
                ChatCompletionChoice(
                    message=ChatMessage(role="assistant", content=result.content),
                    finish_reason=result.finish_reason,
                )
            ],
            daari_meta=result.daari_meta.model_dump(),
        ).model_dump()

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/v1/daari/stats")
    async def daari_stats(request: Request) -> dict[str, Any]:
        ctx: AppContext = request.app.state.ctx
        snapshot = ctx.metrics.snapshot()
        total = sum(t["count"] for t in snapshot.values())
        return {"total_requests": total, "errors": ctx.metrics.errors, "tiers": snapshot}

    return router

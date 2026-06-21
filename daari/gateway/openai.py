from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from daari.gateway.base import GatewayAdapter
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


class OpenAIGatewayAdapter(GatewayAdapter):
    id = "openai"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/chat/completions", response_model=None)
        async def chat_completions(
            body: ChatCompletionRequest,
            request: Request,
            x_daari_no_cache: str | None = Header(default=None, alias="X-Daari-No-Cache"),
            x_daari_tier_override: str | None = Header(default=None, alias="X-Daari-Tier-Override"),
            x_daari_no_frontier: str | None = Header(default=None, alias="X-Daari-No-Frontier"),
            x_daari_confirm_tool: str | None = Header(default=None, alias="X-Daari-Confirm-Tool"),
            x_daari_confirm: str | None = Header(default=None, alias="X-Daari-Confirm"),
            x_daari_rerun_command: str | None = Header(default=None, alias="X-Daari-ReRun-Command"),
        ) -> Any:
            confirm_value = (x_daari_confirm or x_daari_confirm_tool or "").strip().lower()
            confirm_tool = confirm_value in {"1", "true", "yes"}

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
                    no_frontier=x_daari_no_frontier == "true",
                    confirm_tool=confirm_tool,
                    rerun_command=x_daari_rerun_command == "true",
                ),
            )

            if body.stream:

                async def event_stream() -> AsyncIterator[str]:
                    try:
                        async for chunk in ctx.router.stream_openai_chunks(internal):
                            yield chunk
                    except Exception as exc:
                        yield f"data: {{\"error\": \"stream failed: {str(exc)}\"}}\n\n"
                        yield "data: [DONE]\n\n"

                return StreamingResponse(event_stream(), media_type="text/event-stream")

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

        @router.post("/v1/daari/reload-caches")
        async def daari_reload_caches(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            payload = ctx.reload_cache_handles()
            return {"status": "ok", **payload}

        @router.post("/v1/org-learning/sync")
        async def org_learning_sync(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            if ctx.org_learning_client is None:
                raise HTTPException(status_code=404, detail="org learning is not configured")
            changed = await ctx.sync_org_learning_profile_once()
            return {
                "status": "ok",
                "changed": changed,
                "routing": {
                    "prefer": ctx.router.model_preference,
                    "confidence_threshold": ctx.router.confidence_threshold,
                },
            }

        return router


def create_gateway_router() -> APIRouter:
    return OpenAIGatewayAdapter().router()

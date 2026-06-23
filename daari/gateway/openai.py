from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from daari.gateway.base import GatewayAdapter
from daari.gateway.content import content_to_text, sanitize_messages_for_ollama
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.request_log import log_gateway_event
from daari.router.router import AppContext

OPENAI_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

PLAIN_TEXT_HINT = (
    "Respond in plain natural language only. Do not call tools and do not return JSON tool calls."
)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str | list[dict[str, Any]] | dict[str, Any] | None = None
    tool_calls: list[Any] | None = None


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    tools: list[Any] | None = None
    stream: bool = False
    stream_options: dict[str, Any] | None = None


def _to_internal_messages(messages: list[ChatMessage]) -> list[Message]:
    internal: list[Message] = []
    for message in messages:
        text = content_to_text(message.content)
        role = message.role
        if role == "developer":
            role = "system"
        if role == "assistant" and not text and not message.tool_calls:
            continue
        if role in {"user", "system"} and not text:
            continue
        internal.append(
            Message(
                role=role,
                content=text,
                tool_calls=message.tool_calls,
            )
        )
    return internal


def _prepare_internal_request(
    body: ChatCompletionRequest,
    *,
    default_model: str,
    meta: RequestMeta,
) -> InternalRequest:
    """Normalize Cursor/BYOK payloads for local text chat."""
    messages = _to_internal_messages(body.messages)
    user_messages = sum(1 for message in messages if message.role == "user")
    if user_messages == 0:
        raw_types = [
            {
                "role": message.role,
                "content_type": type(message.content).__name__,
                "block_types": [
                    block.get("type")
                    for block in (message.content if isinstance(message.content, list) else [])
                    if isinstance(block, dict)
                ],
            }
            for message in body.messages
        ]
        log_gateway_event("no_user_messages_after_normalize", {"raw": raw_types, "model": body.model})
    tools = body.tools
    if tools:
        log_gateway_event("tools_stripped", {"count": len(tools), "model": body.model})
        tools = None
        if messages and messages[0].role == "system":
            prefix = messages[0].content or ""
            if PLAIN_TEXT_HINT not in prefix:
                messages[0] = Message(role="system", content=f"{prefix}\n\n{PLAIN_TEXT_HINT}".strip())
        else:
            messages.insert(0, Message(role="system", content=PLAIN_TEXT_HINT))
        messages = sanitize_messages_for_ollama(messages)
    return InternalRequest(
        messages=messages,
        model=body.model or default_model,
        temperature=body.temperature,
        tools=tools,
        stream=body.stream,
        meta=meta,
    )


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
    usage: dict[str, int] = Field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
    daari_meta: dict[str, Any] | None = None


def _openai_completion_body(
    *,
    body: ChatCompletionRequest,
    result_content: str,
    result_model: str,
    daari_meta: dict[str, Any] | None,
    include_daari_meta: bool,
) -> dict[str, Any]:
    prompt_chars = sum(len(message.content or "") for message in body.messages)
    completion_chars = len(result_content)
    payload = ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
        created=int(time.time()),
        model=body.model or result_model,
        choices=[
            ChatCompletionChoice(
                message=ChatMessage(role="assistant", content=result_content),
                finish_reason="stop",
            )
        ],
        usage={
            "prompt_tokens": max(1, prompt_chars // 4),
            "completion_tokens": max(0, completion_chars // 4),
            "total_tokens": max(1, (prompt_chars + completion_chars) // 4),
        },
        daari_meta=daari_meta if include_daari_meta else None,
    )
    return payload.model_dump(exclude_none=True)


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
            x_daari_meta: str | None = Header(default=None, alias="X-Daari-Meta"),
        ) -> Any:
            confirm_value = (x_daari_confirm or x_daari_confirm_tool or "").strip().lower()
            confirm_tool = confirm_value in {"1", "true", "yes"}
            include_daari_meta = (x_daari_meta or "").strip().lower() in {"1", "true", "yes"}
            include_usage = bool(body.stream_options and body.stream_options.get("include_usage"))
            client_host = request.client.host if request.client else "unknown"
            user_agent = request.headers.get("user-agent", "")
            log_gateway_event(
                "chat_completions_request",
                {
                    "client": client_host,
                    "user_agent": user_agent[:200],
                    "model": body.model,
                    "stream": body.stream,
                    "stream_options": body.stream_options,
                    "message_count": len(body.messages),
                    "roles": [message.role for message in body.messages],
                    "tools": len(body.tools or []),
                },
            )

            ctx: AppContext = request.app.state.ctx
            internal = _prepare_internal_request(
                body,
                default_model=ctx.settings.models.l3,
                meta=RequestMeta(
                    no_cache=x_daari_no_cache == "true",
                    tier_override=x_daari_tier_override,
                    no_frontier=x_daari_no_frontier == "true",
                    confirm_tool=confirm_tool,
                    rerun_command=x_daari_rerun_command == "true",
                    stream_include_usage=include_usage,
                ),
            )

            if body.stream:

                async def event_stream() -> AsyncIterator[str]:
                    content_chars = 0
                    try:
                        async for chunk in ctx.router.stream_openai_chunks(internal):
                            if '"delta": {"content":' in chunk or '"delta":{"content":' in chunk:
                                content_chars += 1
                            yield chunk
                    except Exception as exc:
                        yield f"data: {json.dumps({'error': f'stream failed: {exc}'})}\n\n"
                        yield "data: [DONE]\n\n"
                    finally:
                        log_gateway_event(
                            "chat_completions_stream_done",
                            {
                                "client": client_host,
                                "model": body.model,
                                "content_chunks": content_chars,
                            },
                        )

                return StreamingResponse(
                    event_stream(),
                    media_type="text/event-stream",
                    headers=OPENAI_SSE_HEADERS,
                )

            try:
                result = await ctx.router.route(internal)
            except Exception as exc:
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=f"Routing failed: {exc}") from exc

            return _openai_completion_body(
                body=body,
                result_content=result.content,
                result_model=result.model,
                daari_meta=result.daari_meta.model_dump(exclude_none=True),
                include_daari_meta=include_daari_meta,
            )

        @router.get("/v1/models")
        async def list_models(request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            created = int(time.time())
            model_ids = ["daari", ctx.settings.models.l3, ctx.settings.models.l4, ctx.settings.models.l5]
            unique_ids: list[str] = []
            for model_id in model_ids:
                if model_id not in unique_ids:
                    unique_ids.append(model_id)
            return {
                "object": "list",
                "data": [
                    {
                        "id": model_id,
                        "object": "model",
                        "created": created,
                        "owned_by": "daari" if model_id == "daari" else "ollama",
                    }
                    for model_id in unique_ids
                ],
            }

        @router.get("/v1/models/{model_id}")
        async def retrieve_model(model_id: str) -> dict[str, Any]:
            return {
                "id": model_id,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "daari" if model_id == "daari" else "ollama",
            }

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

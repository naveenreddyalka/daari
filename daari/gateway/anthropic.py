from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from daari.gateway.base import GatewayAdapter
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.router.router import AppContext


class AnthropicMessageIn(BaseModel):
    role: str
    content: str | list[dict[str, Any]]


class AnthropicRequest(BaseModel):
    model: str
    messages: list[AnthropicMessageIn]
    max_tokens: int | None = None
    stream: bool = False
    temperature: float = 0.7


class AnthropicTextBlock(BaseModel):
    type: str = "text"
    text: str


class AnthropicMessageResponse(BaseModel):
    id: str
    type: str = "message"
    role: str = "assistant"
    model: str
    content: list[AnthropicTextBlock]
    stop_reason: str = "end_turn"
    stop_sequence: str | None = None
    usage: dict[str, int] = Field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    daari_meta: dict[str, Any] = Field(default_factory=dict)


def _content_to_text(content: str | list[dict[str, Any]]) -> str:
    if isinstance(content, str):
        return content
    text_parts: list[str] = []
    for block in content:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
    return "\n".join(part for part in text_parts if part)


class AnthropicGatewayAdapter(GatewayAdapter):
    id = "anthropic"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/messages", response_model=None)
        async def messages(
            body: AnthropicRequest,
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
                messages=[
                    Message(role=message.role, content=_content_to_text(message.content))
                    for message in body.messages
                ],
                model=body.model or ctx.settings.models.l3,
                temperature=body.temperature,
                stream=False,
                meta=RequestMeta(
                    no_cache=x_daari_no_cache == "true",
                    tier_override=x_daari_tier_override,
                    no_frontier=x_daari_no_frontier == "true",
                    confirm_tool=confirm_tool,
                    rerun_command=x_daari_rerun_command == "true",
                ),
            )

            if body.stream:
                internal.stream = True

                async def event_stream():
                    try:
                        async for event in ctx.router.stream_anthropic_events(internal):
                            yield event
                    except Exception as exc:
                        error_payload = {
                            "type": "error",
                            "error": {"type": "stream_error", "message": str(exc)},
                        }
                        yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"
                        # Gracefully fall back to a non-streamed route and re-emit as a single SSE message.
                        fallback = internal.model_copy(deep=True)
                        fallback.stream = False
                        fallback_result = await ctx.router.route(fallback)
                        fallback_meta = fallback_result.daari_meta.model_dump()
                        fallback_meta["warning"] = "stream_failed_fell_back_to_non_stream"
                        message_start = {
                            "type": "message_start",
                            "message": {
                                "id": f"msg_{uuid.uuid4().hex[:12]}",
                                "type": "message",
                                "role": "assistant",
                                "model": fallback_result.model,
                                "content": [],
                                "stop_reason": None,
                                "stop_sequence": None,
                                "usage": {"input_tokens": 0, "output_tokens": 0},
                            },
                            "daari_meta": fallback_meta,
                        }
                        yield f"event: message_start\ndata: {json.dumps(message_start)}\n\n"
                        block_start = {
                            "type": "content_block_start",
                            "index": 0,
                            "content_block": {"type": "text", "text": ""},
                            "daari_meta": fallback_meta,
                        }
                        yield f"event: content_block_start\ndata: {json.dumps(block_start)}\n\n"
                        block_delta = {
                            "type": "content_block_delta",
                            "index": 0,
                            "delta": {"type": "text_delta", "text": fallback_result.content},
                            "daari_meta": fallback_meta,
                        }
                        yield f"event: content_block_delta\ndata: {json.dumps(block_delta)}\n\n"
                        yield f"event: content_block_stop\ndata: {json.dumps({'type': 'content_block_stop', 'index': 0, 'daari_meta': fallback_meta})}\n\n"
                        yield f"event: message_delta\ndata: {json.dumps({'type': 'message_delta', 'delta': {'stop_reason': 'end_turn', 'stop_sequence': None}, 'usage': {'output_tokens': 0}, 'daari_meta': fallback_meta})}\n\n"
                        yield f"event: message_stop\ndata: {json.dumps({'type': 'message_stop', 'daari_meta': fallback_meta})}\n\n"

                return StreamingResponse(event_stream(), media_type="text/event-stream")

            try:
                result = await ctx.router.route(internal)
            except Exception as exc:
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=f"Routing failed: {exc}") from exc

            return AnthropicMessageResponse(
                id=f"msg_{uuid.uuid4().hex[:12]}",
                model=result.model,
                content=[AnthropicTextBlock(text=result.content)],
                daari_meta=result.daari_meta.model_dump(),
            ).model_dump()

        @router.get("/v1/messages/health")
        async def health() -> dict[str, str]:
            return {"status": "ok", "adapter": "anthropic", "time": str(int(time.time()))}

        return router

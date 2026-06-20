from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
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
            x_daari_rerun_command: str | None = Header(default=None, alias="X-Daari-ReRun-Command"),
        ) -> dict[str, Any]:
            if body.stream:
                raise HTTPException(status_code=501, detail="Anthropic streaming is not implemented yet.")

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
                    confirm_tool=x_daari_confirm_tool == "true",
                    rerun_command=x_daari_rerun_command == "true",
                ),
            )

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

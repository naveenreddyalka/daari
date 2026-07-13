from __future__ import annotations

import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from daari.gateway.base import GatewayAdapter
from daari.gateway.content import content_to_text
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.request_log import log_gateway_event
from daari.router.router import AppContext


class AnthropicMessageIn(BaseModel):
    role: str
    content: str | list[dict[str, Any]]


def anthropic_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Anthropic {name, description, input_schema} -> OpenAI function-tool shape.

    The Ollama executor (and frontier providers) speak the OpenAI tools format.
    """
    converted: list[dict[str, Any]] = []
    for tool in tools:
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description") or "",
                    "parameters": tool.get("input_schema") or {"type": "object", "properties": {}},
                },
            }
        )
    return converted


def anthropic_message_to_internal(message: AnthropicMessageIn) -> list[Message]:
    """Expand one Anthropic message into internal messages.

    Assistant `tool_use` blocks become OpenAI-style tool_calls; user
    `tool_result` blocks become role=tool messages (issue #84). Plain text
    stays a single message.
    """
    if isinstance(message.content, str):
        text = content_to_text(message.content)
        return [Message(role=message.role, content=text)] if text else []

    text_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[Message] = []
    for block in message.content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "tool_use":
            arguments = block.get("input")
            tool_calls.append(
                {
                    "id": block.get("id") or f"toolu_{uuid.uuid4().hex[:24]}",
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(arguments if isinstance(arguments, dict) else {}),
                    },
                }
            )
        elif block_type == "tool_result":
            result_text = content_to_text(block.get("content")) or ""
            tool_results.append(Message(role="tool", content=result_text))
        else:
            text = content_to_text([block])
            if text:
                text_parts.append(text)

    expanded: list[Message] = []
    joined = "\n".join(text_parts) or None
    if tool_calls:
        expanded.append(Message(role=message.role, content=joined, tool_calls=tool_calls))
    elif joined:
        expanded.append(Message(role=message.role, content=joined))
    expanded.extend(tool_results)
    return expanded


class AnthropicRequest(BaseModel):
    model: str
    messages: list[AnthropicMessageIn]
    # Anthropic clients (e.g. Claude Code) send the system prompt as a
    # top-level field rather than a system-role message.
    system: str | list[dict[str, Any]] | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: dict[str, Any] | None = None
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
            x_daari_tools: str | None = Header(default=None, alias="X-Daari-Tools"),
        ) -> Any:
            confirm_value = (x_daari_confirm or x_daari_confirm_tool or "").strip().lower()
            confirm_tool = confirm_value in {"1", "true", "yes"}

            ctx: AppContext = request.app.state.ctx
            # Request-shape log (issue #88): mirrors chat_completions_request so
            # live failures are diagnosable from cursor-requests.log.
            log_gateway_event(
                "anthropic_messages_request",
                {
                    "client": request.client.host if request.client else None,
                    "user_agent": request.headers.get("user-agent"),
                    "model": body.model,
                    "stream": body.stream,
                    "message_count": len(body.messages),
                    "roles": [message.role for message in body.messages],
                    "tools": len(body.tools or []),
                    "system_chars": len(content_to_text(body.system) or ""),
                    "prompt_chars": sum(
                        len(content_to_text(message.content) or "") for message in body.messages
                    ),
                },
            )
            internal_messages: list[Message] = []
            system_text = content_to_text(body.system)
            if system_text:
                internal_messages.append(Message(role="system", content=system_text))
            for message in body.messages:
                internal_messages.extend(anthropic_message_to_internal(message))

            # Tool passthrough (issue #84): Claude Code agent turns carry tools;
            # X-Daari-Tools: strip forces plain-chat handling for parity with
            # the OpenAI gateway.
            tools_mode = (x_daari_tools or "").strip().lower()
            internal_tools = None
            if body.tools and tools_mode != "strip":
                internal_tools = anthropic_tools_to_openai(body.tools) or None

            internal = InternalRequest(
                messages=internal_messages,
                tools=internal_tools,
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

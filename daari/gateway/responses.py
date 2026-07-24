"""OpenAI Responses API adapter (issue #108, ROADMAP-v2 Train F2).

New OpenAI SDKs default to `POST /v1/responses` instead of chat completions.
This adapter converts Responses-shaped requests into InternalRequest and maps
routed results back — non-stream and SSE. Text conversations are fully
supported; `tools` are accepted and forwarded to the router (agent flows keep
the tool protocol), but function-call *output* items are not emitted yet —
tool-using agents should stay on /v1/chat/completions or /v1/messages.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from daari.config.project import apply_profile_to_meta, load_project_profile
from daari.gateway.base import GatewayAdapter
from daari.gateway.internal import InternalRequest, InternalResponse, Message, RequestMeta
from daari.gateway.request_log import log_gateway_event
from daari.router.router import AppContext

SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive"}


class ResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = ""
    input: str | list[dict[str, Any]] = ""
    instructions: str | None = None
    temperature: float | None = None
    stream: bool = False
    tools: list[dict[str, Any]] | None = None
    max_output_tokens: int | None = None


def _content_to_text(content: Any) -> str:
    """Responses items carry content as a string or typed part list."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return ""


def responses_input_to_messages(body: ResponsesRequest) -> list[Message]:
    messages: list[Message] = []
    if body.instructions:
        messages.append(Message(role="system", content=body.instructions))
    if isinstance(body.input, str):
        messages.append(Message(role="user", content=body.input))
        return messages
    for item in body.input:
        item_type = item.get("type", "message")
        if item_type != "message":
            # function_call / function_call_output replay is out of scope for
            # the v1 adapter (see module docstring); skip rather than 500.
            continue
        role = item.get("role", "user")
        messages.append(Message(role=role, content=_content_to_text(item.get("content"))))
    return messages


def responses_tools_to_openai(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Responses tools are flat; internal/chat tools nest under "function"."""
    converted = []
    for tool in tools:
        if tool.get("type") == "function" and "function" not in tool:
            converted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {}),
                    },
                }
            )
        else:
            converted.append(tool)
    return converted


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _response_body(
    response_id: str,
    result: InternalResponse,
    *,
    input_chars: int,
    include_daari_meta: bool,
) -> dict[str, Any]:
    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    body: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": result.model,
        "output": [
            {
                "type": "message",
                "id": message_id,
                "status": "completed",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": result.content, "annotations": []}
                ],
            }
        ],
        "usage": {
            "input_tokens": _estimate_tokens("x" * input_chars),
            "output_tokens": _estimate_tokens(result.content),
            "total_tokens": _estimate_tokens("x" * input_chars)
            + _estimate_tokens(result.content),
        },
    }
    if include_daari_meta:
        body["daari_meta"] = result.daari_meta.model_dump(exclude_none=True)
    return body


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _delta_from_chat_chunk(raw: str) -> str | None:
    """Extract the text delta from one `data: {...}` chat-completions chunk."""
    line = raw.strip()
    if not line.startswith("data:"):
        return None
    data = line[len("data:") :].strip()
    if data == "[DONE]":
        return None
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = parsed.get("choices") or []
    if not choices:
        return None
    return (choices[0].get("delta") or {}).get("content")


class ResponsesGatewayAdapter(GatewayAdapter):
    id = "responses"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.post("/v1/responses", response_model=None)
        async def responses(
            body: ResponsesRequest,
            request: Request,
            x_daari_no_cache: str | None = Header(default=None, alias="X-Daari-No-Cache"),
            x_daari_tier_override: str | None = Header(default=None, alias="X-Daari-Tier-Override"),
            x_daari_tier_cap: str | None = Header(default=None, alias="X-Daari-Tier-Cap"),
            x_daari_no_frontier: str | None = Header(default=None, alias="X-Daari-No-Frontier"),
            x_daari_latency_budget: str | None = Header(default=None, alias="X-Daari-Latency-Budget"),
            x_daari_client_id: str | None = Header(default=None, alias="X-Daari-Client-Id"),
            x_daari_meta: str | None = Header(default=None, alias="X-Daari-Meta"),
            x_daari_project: str | None = Header(default=None, alias="X-Daari-Project"),
        ) -> Any:
            ctx: AppContext = request.app.state.ctx
            include_daari_meta = (x_daari_meta or "").strip().lower() in {"1", "true", "yes"}
            try:
                latency_budget_ms = int(x_daari_latency_budget) if x_daari_latency_budget else None
            except ValueError:
                latency_budget_ms = None

            messages = responses_input_to_messages(body)
            if not messages:
                raise HTTPException(status_code=400, detail="input produced no messages")
            meta = RequestMeta(
                no_cache=x_daari_no_cache == "true",
                tier_override=x_daari_tier_override,
                tier_cap=x_daari_tier_cap,
                latency_budget_ms=latency_budget_ms,
                client_id=x_daari_client_id,
                no_frontier=x_daari_no_frontier == "true",
            )
            apply_profile_to_meta(meta, load_project_profile(x_daari_project))
            internal = InternalRequest(
                messages=messages,
                model=body.model or ctx.settings.models.l3,
                temperature=body.temperature if body.temperature is not None else 0.7,
                tools=responses_tools_to_openai(body.tools) if body.tools else None,
                stream=body.stream,
                meta=meta,
            )
            input_chars = sum(len(message.content or "") for message in messages)
            log_gateway_event(
                "responses_request",
                {
                    "model": internal.model,
                    "stream": body.stream,
                    "message_count": len(messages),
                    "tools": len(body.tools or []),
                    "input_chars": input_chars,
                },
            )
            response_id = f"resp_{uuid.uuid4().hex[:16]}"

            if body.stream:
                return StreamingResponse(
                    self._event_stream(ctx, internal, response_id, input_chars),
                    media_type="text/event-stream",
                    headers=SSE_HEADERS,
                )

            try:
                result = await ctx.router.route(internal)
            except Exception as exc:
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=f"Routing failed: {exc}") from exc
            return _response_body(
                response_id,
                result,
                input_chars=input_chars,
                include_daari_meta=include_daari_meta,
            )

        return router

    @staticmethod
    async def _event_stream(
        ctx: AppContext,
        internal: InternalRequest,
        response_id: str,
        input_chars: int,
    ) -> AsyncIterator[str]:
        """Re-emit the routed chat-completions stream as Responses events,
        so streaming reuses the full tier chain (caches, fallback, budgets)."""
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        base = {"id": response_id, "object": "response", "model": internal.model}
        yield _sse(
            "response.created",
            {"type": "response.created", "response": {**base, "status": "in_progress"}},
        )
        item = {"type": "message", "id": message_id, "role": "assistant", "status": "in_progress"}
        yield _sse(
            "response.output_item.added",
            {"type": "response.output_item.added", "output_index": 0, "item": item},
        )
        yield _sse(
            "response.content_part.added",
            {
                "type": "response.content_part.added",
                "item_id": message_id,
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text", "text": "", "annotations": []},
            },
        )
        collected: list[str] = []
        try:
            async for chunk in ctx.router.stream_openai_chunks(internal):
                delta = _delta_from_chat_chunk(chunk)
                if not delta:
                    continue
                collected.append(delta)
                yield _sse(
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "item_id": message_id,
                        "output_index": 0,
                        "content_index": 0,
                        "delta": delta,
                    },
                )
        except Exception as exc:
            yield _sse(
                "response.failed",
                {
                    "type": "response.failed",
                    "response": {
                        **base,
                        "status": "failed",
                        "error": {"code": "server_error", "message": str(exc)[:300]},
                    },
                },
            )
            return
        text = "".join(collected)
        yield _sse(
            "response.output_text.done",
            {
                "type": "response.output_text.done",
                "item_id": message_id,
                "output_index": 0,
                "content_index": 0,
                "text": text,
            },
        )
        completed_item = {
            "type": "message",
            "id": message_id,
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }
        yield _sse(
            "response.output_item.done",
            {"type": "response.output_item.done", "output_index": 0, "item": completed_item},
        )
        yield _sse(
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    **base,
                    "status": "completed",
                    "output": [completed_item],
                    "usage": {
                        "input_tokens": _estimate_tokens("x" * input_chars),
                        "output_tokens": _estimate_tokens(text),
                        "total_tokens": _estimate_tokens("x" * input_chars)
                        + _estimate_tokens(text),
                    },
                },
            },
        )
        log_gateway_event(
            "responses_stream_done",
            {"model": internal.model, "completion_chars": len(text)},
        )

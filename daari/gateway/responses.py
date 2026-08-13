"""OpenAI Responses API adapter (issues #108, #165).

Function-call items round-trip, previous_response_id chains stored turns,
background mode is pollable via GET, and include/metadata are never dropped
silently.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from daari.config.project import apply_profile_to_meta, load_project_profile
from daari.gateway.base import GatewayAdapter
from daari.gateway.content import extract_images
from daari.gateway.internal import InternalRequest, InternalResponse, Message, RequestMeta
from daari.gateway.request_log import log_gateway_event
from daari.gateway.response_store import ResponseStore
from daari.gateway.sampling import SamplingParams
from daari.router.capabilities import UnsupportedCapability
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
    previous_response_id: str | None = None
    store: bool = True
    background: bool = False
    include: list[str] | None = None
    metadata: dict[str, str] | None = None


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
        if item_type == "function_call":
            call_id = str(item.get("call_id") or item.get("id") or f"call_{uuid.uuid4().hex[:8]}")
            arguments = item.get("arguments") or "{}"
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments)
            messages.append(
                Message(
                    role="assistant",
                    content="",
                    tool_calls=[
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": item.get("name") or "",
                                "arguments": arguments,
                            },
                        }
                    ],
                )
            )
            continue
        if item_type == "function_call_output":
            messages.append(
                Message(
                    role="tool",
                    content=str(item.get("output") or ""),
                    tool_call_id=item.get("call_id"),
                )
            )
            continue
        if item_type != "message":
            continue
        role = item.get("role", "user")
        content = item.get("content")
        messages.append(
            Message(
                role=role,
                content=_content_to_text(content),
                images=extract_images(content),
            )
        )
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


def _tool_calls_to_output_items(tool_calls: list[Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments)
        items.append(
            {
                "type": "function_call",
                "id": f"fc_{uuid.uuid4().hex[:12]}",
                "call_id": call.get("id") or f"call_{uuid.uuid4().hex[:8]}",
                "name": function.get("name") or "",
                "arguments": arguments,
                "status": "completed",
            }
        )
    return items


def _output_items_from_result(result: InternalResponse) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if result.tool_calls:
        items.extend(_tool_calls_to_output_items(result.tool_calls))
    if result.content or not items:
        items.append(
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:12]}",
                "status": "completed",
                "role": "assistant",
                "content": [{"type": "output_text", "text": result.content or "", "annotations": []}],
            }
        )
    return items


def _conversation_after(messages: list[Message], output: list[dict[str, Any]]) -> list[dict[str, Any]]:
    history = [message.model_dump(exclude_none=True) for message in messages]
    for item in output:
        if item.get("type") == "function_call":
            history.append(
                Message(
                    role="assistant",
                    content="",
                    tool_calls=[
                        {
                            "id": item.get("call_id"),
                            "type": "function",
                            "function": {
                                "name": item.get("name") or "",
                                "arguments": item.get("arguments") or "{}",
                            },
                        }
                    ],
                ).model_dump(exclude_none=True)
            )
        elif item.get("type") == "message":
            history.append(
                Message(role="assistant", content=_content_to_text(item.get("content"))).model_dump(
                    exclude_none=True
                )
            )
    return history


def _response_body(
    response_id: str,
    result: InternalResponse,
    *,
    input_chars: int,
    include_daari_meta: bool,
    metadata: dict[str, str] | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": status,
        "model": result.model,
        "output": _output_items_from_result(result) if status == "completed" else [],
        "usage": {
            "input_tokens": _estimate_tokens("x" * input_chars),
            "output_tokens": _estimate_tokens(result.content),
            "total_tokens": _estimate_tokens("x" * input_chars) + _estimate_tokens(result.content),
        },
    }
    if metadata is not None:
        body["metadata"] = metadata
    if include_daari_meta:
        body["daari_meta"] = result.daari_meta.model_dump(exclude_none=True)
    return body


def _public_body(stored: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in stored.items() if not key.startswith("_")}


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def _parse_chat_delta(raw: str) -> dict[str, Any] | None:
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
    delta = choices[0].get("delta")
    return delta if isinstance(delta, dict) else None


def _store_for(ctx: AppContext) -> ResponseStore:
    return ResponseStore(Path(ctx.settings.trace.path).expanduser().parent / "responses.sqlite3")


class ResponsesGatewayAdapter(GatewayAdapter):
    id = "responses"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/v1/responses/{response_id}")
        async def get_response(response_id: str, request: Request) -> dict[str, Any]:
            stored = _store_for(request.app.state.ctx).get(response_id)
            if stored is None:
                raise HTTPException(status_code=404, detail="response not found")
            return _public_body(stored)

        @router.post("/v1/responses", response_model=None)
        async def responses(
            body: ResponsesRequest,
            request: Request,
            background_tasks: BackgroundTasks,
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
            if body.include:
                raise HTTPException(
                    status_code=400,
                    detail=f"include is not supported: {body.include}",
                )
            include_daari_meta = (x_daari_meta or "").strip().lower() in {"1", "true", "yes"}
            try:
                latency_budget_ms = int(x_daari_latency_budget) if x_daari_latency_budget else None
            except ValueError:
                latency_budget_ms = None

            store = _store_for(ctx)
            messages = responses_input_to_messages(body)
            if body.previous_response_id:
                prior = store.get(body.previous_response_id)
                if prior is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"previous_response_id not found: {body.previous_response_id}",
                    )
                prior_messages = [
                    Message.model_validate(item) for item in prior.get("_conversation") or []
                ]
                messages = prior_messages + messages
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
            from daari.server.auth import apply_auth_claims_to_meta

            apply_auth_claims_to_meta(meta, getattr(request.state, "auth_claims", None))
            apply_profile_to_meta(meta, load_project_profile(x_daari_project))
            internal = InternalRequest(
                messages=messages,
                model=body.model or ctx.settings.models.l3,
                temperature=body.temperature if body.temperature is not None else 0.7,
                tools=responses_tools_to_openai(body.tools) if body.tools else None,
                stream=body.stream and not body.background,
                meta=meta,
                sampling=SamplingParams.from_responses_body(body.model_dump()),
            )
            input_chars = sum(len(message.content or "") for message in messages)
            log_gateway_event(
                "responses_request",
                {
                    "model": internal.model,
                    "stream": internal.stream,
                    "message_count": len(messages),
                    "tools": len(body.tools or []),
                    "input_chars": input_chars,
                    "background": body.background,
                },
            )
            response_id = f"resp_{uuid.uuid4().hex[:16]}"

            if body.stream and not body.background:
                return StreamingResponse(
                    self._event_stream(
                        ctx,
                        internal,
                        response_id,
                        input_chars,
                        metadata=body.metadata,
                        store=store if body.store else None,
                        history=messages,
                    ),
                    media_type="text/event-stream",
                    headers=SSE_HEADERS,
                )

            if body.background:
                queued = {
                    "id": response_id,
                    "object": "response",
                    "created_at": int(time.time()),
                    "status": "queued",
                    "model": internal.model,
                    "output": [],
                }
                if body.metadata is not None:
                    queued["metadata"] = body.metadata
                store.put(response_id, queued, conversation=[], stored=True)
                background_tasks.add_task(
                    self._run_background,
                    ctx,
                    internal,
                    response_id,
                    input_chars,
                    include_daari_meta,
                    body.metadata,
                    messages,
                    store,
                )
                return queued

            try:
                result = await ctx.router.route(internal)
            except UnsupportedCapability as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except Exception as exc:
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=f"Routing failed: {exc}") from exc
            payload = _response_body(
                response_id,
                result,
                input_chars=input_chars,
                include_daari_meta=include_daari_meta,
                metadata=body.metadata,
            )
            store.put(
                response_id,
                payload,
                conversation=_conversation_after(messages, payload["output"]),
                stored=body.store,
            )
            return payload

        return router

    @staticmethod
    async def _run_background(
        ctx: AppContext,
        internal: InternalRequest,
        response_id: str,
        input_chars: int,
        include_daari_meta: bool,
        metadata: dict[str, str] | None,
        history: list[Message],
        store: ResponseStore,
    ) -> None:
        try:
            result = await ctx.router.route(internal)
            payload = _response_body(
                response_id,
                result,
                input_chars=input_chars,
                include_daari_meta=include_daari_meta,
                metadata=metadata,
            )
            store.put(
                response_id,
                payload,
                conversation=_conversation_after(history, payload["output"]),
                stored=True,
            )
        except Exception as exc:  # noqa: BLE001 — persist failure for GET polling
            store.put(
                response_id,
                {
                    "id": response_id,
                    "object": "response",
                    "status": "failed",
                    "error": {"code": "server_error", "message": str(exc)[:300]},
                    "output": [],
                },
                conversation=[],
                stored=True,
            )

    @staticmethod
    async def _event_stream(
        ctx: AppContext,
        internal: InternalRequest,
        response_id: str,
        input_chars: int,
        *,
        metadata: dict[str, str] | None = None,
        store: ResponseStore | None = None,
        history: list[Message] | None = None,
    ) -> AsyncIterator[str]:
        """Re-emit the routed chat-completions stream as Responses events."""
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
        tool_acc: dict[int, dict[str, str]] = {}
        tool_item_ids: dict[int, str] = {}
        try:
            async for chunk in ctx.router.stream_openai_chunks(internal):
                delta = _parse_chat_delta(chunk)
                if not delta:
                    continue
                text_delta = delta.get("content")
                if text_delta:
                    collected.append(text_delta)
                    yield _sse(
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "item_id": message_id,
                            "output_index": 0,
                            "content_index": 0,
                            "delta": text_delta,
                        },
                    )
                for call in delta.get("tool_calls") or []:
                    if not isinstance(call, dict):
                        continue
                    index = int(call.get("index") or 0)
                    slot = tool_acc.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if call.get("id"):
                        slot["id"] = str(call["id"])
                    function = call.get("function") or {}
                    if function.get("name"):
                        slot["name"] = str(function["name"])
                    piece = function.get("arguments")
                    if not piece:
                        continue
                    slot["arguments"] += str(piece)
                    if index not in tool_item_ids:
                        item_id = f"fc_{uuid.uuid4().hex[:12]}"
                        tool_item_ids[index] = item_id
                        yield _sse(
                            "response.output_item.added",
                            {
                                "type": "response.output_item.added",
                                "output_index": index + 1,
                                "item": {
                                    "type": "function_call",
                                    "id": item_id,
                                    "call_id": slot["id"],
                                    "name": slot["name"],
                                    "arguments": "",
                                    "status": "in_progress",
                                },
                            },
                        )
                    yield _sse(
                        "response.function_call_arguments.delta",
                        {
                            "type": "response.function_call_arguments.delta",
                            "item_id": tool_item_ids[index],
                            "output_index": index + 1,
                            "delta": str(piece),
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
        output: list[dict[str, Any]] = []
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
        output.append(completed_item)
        for index, slot in sorted(tool_acc.items()):
            item_id = tool_item_ids.get(index, f"fc_{uuid.uuid4().hex[:12]}")
            yield _sse(
                "response.function_call_arguments.done",
                {
                    "type": "response.function_call_arguments.done",
                    "item_id": item_id,
                    "output_index": index + 1,
                    "arguments": slot["arguments"],
                },
            )
            done_item = {
                "type": "function_call",
                "id": item_id,
                "call_id": slot["id"],
                "name": slot["name"],
                "arguments": slot["arguments"],
                "status": "completed",
            }
            yield _sse(
                "response.output_item.done",
                {"type": "response.output_item.done", "output_index": index + 1, "item": done_item},
            )
            output.append(done_item)
        completed = {
            **base,
            "status": "completed",
            "output": output,
            "usage": {
                "input_tokens": _estimate_tokens("x" * input_chars),
                "output_tokens": _estimate_tokens(text),
                "total_tokens": _estimate_tokens("x" * input_chars) + _estimate_tokens(text),
            },
        }
        if metadata is not None:
            completed["metadata"] = metadata
        yield _sse("response.completed", {"type": "response.completed", "response": completed})
        if store is not None:
            store.put(
                response_id,
                completed,
                conversation=_conversation_after(history or [], output),
                stored=True,
            )
        log_gateway_event(
            "responses_stream_done",
            {"model": internal.model, "completion_chars": len(text)},
        )

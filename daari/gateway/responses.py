"""OpenAI Responses API adapter (issues #108, #165).

Function-call items round-trip, previous_response_id chains stored turns,
background mode is pollable via GET, and include/metadata are never dropped
silently.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from daari.config.project import apply_profile_to_meta, load_project_profile
from daari.gateway.client_errors import backend_unavailable_message, request_deadline_response, routing_failure_detail, safe_detail
from daari.gateway.base import GatewayAdapter
from daari.gateway.cost_tier import apply_cost_tier
from daari.gateway.content import extract_audio, extract_images
from daari.gateway.internal import InternalRequest, InternalResponse, Message, RequestMeta
from daari.gateway.request_log import log_gateway_event
from daari.gateway.response_store import ResponseStore
from daari.gateway.sampling import SamplingParams
from daari.gateway.disconnect import (
    ClientDisconnected,
    await_unless_disconnected,
    note_request_cancelled,
)
from daari.gateway.streaming import SSE_KEEPALIVE_FRAME, stream_with_keepalive
from daari.observability.tokens import estimate_tokens
from daari.router.capabilities import UnsupportedCapability
from daari.router.local_pool import BackendUnavailable
from daari.router.router import AppContext

SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive"}
_BACKGROUND_JOBS: dict[str, asyncio.Task[None]] = {}


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
                audio=extract_audio(content),
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


_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def _visible_stored_response(
    ctx: AppContext, response_id: str, request: Request
) -> tuple[Any, dict[str, Any]]:
    from daari.enterprise.audit import maybe_audit_tenancy_denied
    from daari.gateway.response_store import response_visible_to_caller

    store = _store_for(ctx)
    stored = store.get(response_id)
    claims = getattr(request.state, "auth_claims", None)
    visible = stored is not None and response_visible_to_caller(stored, claims)
    maybe_audit_tenancy_denied(
        ctx.settings,
        claims=claims,
        kind="response",
        artifact_id=response_id,
        stored=stored,
        visible=visible,
    )
    if stored is None or not visible:
        raise HTTPException(status_code=404, detail="response not found")
    return store, stored


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


def _store_for(ctx: AppContext) -> ResponseStore | Any:
    """SQLite by default; postgres when responses.backend=postgres (#481)."""
    settings = ctx.settings
    pg_url = (settings.observability.postgres_url or "").strip()
    if settings.responses.backend == "postgres" and pg_url:
        from daari.gateway.postgres_responses import PostgresResponseStore

        return PostgresResponseStore(pg_url)
    return ResponseStore(Path(settings.trace.path).expanduser().parent / "responses.sqlite3")


def _owner_key_id_from_request(request: Request) -> str | None:
    claims = getattr(request.state, "auth_claims", None)
    if getattr(claims, "kind", None) == "virtual":
        return getattr(claims, "key_id", None)
    return None



class ResponsesGatewayAdapter(GatewayAdapter):
    id = "responses"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/v1/responses/{response_id}")
        async def get_response(response_id: str, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            _store, stored = _visible_stored_response(ctx, response_id, request)
            return _public_body(stored)

        @router.post("/v1/responses/{response_id}/cancel")
        async def cancel_response(response_id: str, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store, stored = _visible_stored_response(ctx, response_id, request)
            if stored.get("status") in _TERMINAL_STATUSES:
                return _public_body(stored)
            cancelled = {
                **_public_body(stored),
                "status": "cancelled",
                "output": stored.get("output") or [],
            }
            store.put(
                response_id,
                cancelled,
                conversation=list(stored.get("_conversation") or []),
                stored=True,
            )
            job = _BACKGROUND_JOBS.pop(response_id, None)
            if job is not None and not job.done():
                job.cancel()
            return cancelled

        @router.delete("/v1/responses/{response_id}")
        async def delete_response(response_id: str, request: Request) -> dict[str, Any]:
            ctx: AppContext = request.app.state.ctx
            store, stored = _visible_stored_response(ctx, response_id, request)
            job = _BACKGROUND_JOBS.pop(response_id, None)
            if job is not None and not job.done():
                job.cancel()
            store.delete(response_id)
            return {"id": stored.get("id") or response_id, "object": "response", "deleted": True}

        @router.post("/v1/responses/input_tokens")
        async def input_tokens(body: ResponsesRequest) -> dict[str, int]:
            """Count prompt tokens locally for Responses clients (#507).

            Ingress helper only — same local `estimate_tokens` path as
            `/v1/messages/count_tokens`, not an L6 round-trip.
            """
            chars = 0
            if body.instructions:
                chars += len(body.instructions)
            for message in responses_input_to_messages(body):
                chars += len(message.content or "")
            if body.tools:
                chars += len(json.dumps(body.tools))
            return {"input_tokens": max(1, estimate_tokens(chars))}

        @router.post("/v1/responses", response_model=None)
        async def responses(
            body: ResponsesRequest,
            request: Request,
            x_daari_no_cache: str | None = Header(default=None, alias="X-Daari-No-Cache"),
            x_daari_tier_override: str | None = Header(default=None, alias="X-Daari-Tier-Override"),
            x_daari_tier_cap: str | None = Header(default=None, alias="X-Daari-Tier-Cap"),
            x_daari_no_frontier: str | None = Header(default=None, alias="X-Daari-No-Frontier"),
            x_daari_latency_budget: str | None = Header(default=None, alias="X-Daari-Latency-Budget"),
            x_daari_deadline_ms: str | None = Header(default=None, alias="X-Daari-Deadline-Ms"),
            x_daari_client_id: str | None = Header(default=None, alias="X-Daari-Client-Id"),
            x_daari_meta: str | None = Header(default=None, alias="X-Daari-Meta"),
            x_daari_project: str | None = Header(default=None, alias="X-Daari-Project"),
        ) -> Any:
            from daari.gateway.response_store import response_visible_to_caller

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
            from daari.router.deadline import RequestDeadlineExceeded, parse_deadline_ms

            deadline_ms = parse_deadline_ms(x_daari_deadline_ms)

            store = _store_for(ctx)
            owner_key_id = _owner_key_id_from_request(request)
            claims = getattr(request.state, "auth_claims", None)
            messages = responses_input_to_messages(body)
            if body.previous_response_id:
                from daari.enterprise.audit import maybe_audit_tenancy_denied

                prior = store.get(body.previous_response_id)
                prior_visible = prior is not None and response_visible_to_caller(prior, claims)
                maybe_audit_tenancy_denied(
                    ctx.settings,
                    claims=claims,
                    kind="response",
                    artifact_id=body.previous_response_id,
                    stored=prior,
                    visible=prior_visible,
                )
                if prior is None or not prior_visible:
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
            from daari.gateway.request_id import request_id_from_request

            request_id = request_id_from_request(request)
            meta = RequestMeta(
                no_cache=x_daari_no_cache == "true",
                tier_override=x_daari_tier_override,
                tier_cap=x_daari_tier_cap,
                latency_budget_ms=latency_budget_ms,
                deadline_ms=deadline_ms,
                client_id=x_daari_client_id,
                no_frontier=x_daari_no_frontier == "true",
                request_id=request_id,
            )
            apply_cost_tier(body, meta)
            from daari.server.auth import apply_auth_claims_to_meta

            apply_auth_claims_to_meta(
                meta,
                claims,
                model_groups=getattr(ctx.settings, "model_groups", None),
            )
            from daari.gateway.model_access import reject_disallowed_model

            denied = reject_disallowed_model(
                request, body.model or ctx.settings.models.l3, ctx.settings, meta
            )
            if denied is not None:
                return denied
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
            from daari.gateway.transcriptions import inject_inline_audio_transcripts

            internal = await inject_inline_audio_transcripts(internal, ctx.settings)
            input_chars = sum(len(message.content or "") for message in internal.messages)
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

            from daari.gateway.idempotency import resolve_idempotency

            idem_kind, idem_response, idem_slot = await resolve_idempotency(
                request, ctx, body
            )
            if idem_kind in {"replay", "conflict"} and idem_response is not None:
                return idem_response

            if body.stream and not body.background:
                async def _idempotent_event_stream() -> AsyncIterator[str]:
                    collected: list[str] = []
                    try:
                        async for chunk in self._event_stream(
                            ctx,
                            internal,
                            response_id,
                            input_chars,
                            metadata=body.metadata,
                            store=store if body.store else None,
                            history=messages,
                            owner_key_id=owner_key_id,
                        ):
                            collected.append(chunk)
                            yield chunk
                    finally:
                        if idem_slot is not None:
                            from daari.gateway.idempotency import (
                                assemble_assistant_text_from_sse,
                            )

                            sse_text = "".join(collected)
                            idem_slot.complete(
                                status_code=200,
                                response_body=sse_text,
                                media_type="text/event-stream",
                                stream=True,
                                assistant_text=assemble_assistant_text_from_sse(sse_text),
                            )

                return StreamingResponse(
                    _idempotent_event_stream(),
                    media_type="text/event-stream",
                    headers={**SSE_HEADERS, "X-Request-ID": request_id},
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
                store.put(
                    response_id,
                    queued,
                    conversation=[],
                    stored=True,
                    owner_key_id=owner_key_id,
                )
                task = asyncio.create_task(
                    self._run_background(
                        ctx,
                        internal,
                        response_id,
                        input_chars,
                        include_daari_meta,
                        body.metadata,
                        messages,
                        store,
                        owner_key_id,
                    )
                )
                _BACKGROUND_JOBS[response_id] = task
                task.add_done_callback(lambda _t, rid=response_id: _BACKGROUND_JOBS.pop(rid, None))
                if idem_slot is not None:
                    idem_slot.complete(
                        status_code=200,
                        response_body=json.dumps(queued, separators=(",", ":")),
                        media_type="application/json",
                        stream=False,
                    )
                return queued

            try:
                result = await await_unless_disconnected(
                    request,
                    ctx.router.route(internal),
                    metrics=ctx.metrics,
                    phase="responses",
                    model=internal.model,
                )
            except ClientDisconnected:
                if idem_slot is not None:
                    idem_slot.abandon()
                return JSONResponse(
                    status_code=499,
                    content={
                        "error": {
                            "type": "client_disconnected",
                            "message": "client disconnected.",
                        }
                    },
                )
            except UnsupportedCapability as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                raise HTTPException(status_code=422, detail=safe_detail(exc)) from exc
            except BackendUnavailable as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                ctx.metrics.record_error()
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "type": "backend_unavailable",
                            "message": backend_unavailable_message(exc),
                        }
                    },
                )
            except RequestDeadlineExceeded as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                return request_deadline_response(exc)
            except Exception as exc:
                if idem_slot is not None:
                    idem_slot.abandon()
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=routing_failure_detail(exc)) from exc
            if getattr(request.state, "request_quota_soft", False):
                result.daari_meta.warning = "request_quota_warning"
            elif getattr(request.state, "budget_soft", False):
                result.daari_meta.warning = "budget_warning"
            elif getattr(request.state, "rate_limit_soft", False):
                result.daari_meta.warning = "rate_limit_warning"
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
                owner_key_id=owner_key_id,
            )
            if idem_slot is not None:
                idem_slot.complete(
                    status_code=200,
                    response_body=json.dumps(payload, separators=(",", ":")),
                    media_type="application/json",
                    stream=False,
                    assistant_text=result.content,
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
        owner_key_id: str | None = None,
    ) -> None:
        try:
            current = store.get(response_id)
            if current is None or current.get("status") == "cancelled":
                return
            result = await ctx.router.route(internal)
            current = store.get(response_id)
            if current is None or current.get("status") == "cancelled":
                return
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
                owner_key_id=owner_key_id,
            )
        except Exception as exc:  # noqa: BLE001 — persist failure for GET polling
            current = store.get(response_id)
            if current is None or current.get("status") == "cancelled":
                return
            store.put(
                response_id,
                {
                    "id": response_id,
                    "object": "response",
                    "status": "failed",
                    "error": {"code": "server_error", "message": safe_detail(exc)[:300]},
                    "output": [],
                },
                conversation=[],
                stored=True,
                owner_key_id=owner_key_id,
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
        owner_key_id: str | None = None,
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
            async for chunk in stream_with_keepalive(
                ctx.router.stream_openai_chunks(internal),
                interval_seconds=ctx.settings.server.sse_keepalive_seconds,
                idle_timeout_seconds=ctx.settings.server.stream_idle_timeout_seconds,
                frame=SSE_KEEPALIVE_FRAME,
                on_cancel=lambda: note_request_cancelled(
                    ctx.metrics, "stream", model=internal.model
                ),
            ):
                if chunk == SSE_KEEPALIVE_FRAME:
                    yield chunk
                    continue
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
                        "error": {"code": "server_error", "message": safe_detail(exc)[:300]},
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
                owner_key_id=owner_key_id,
            )
        log_gateway_event(
            "responses_stream_done",
            {"model": internal.model, "completion_chars": len(text)},
        )

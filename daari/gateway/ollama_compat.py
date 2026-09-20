"""Ollama-compatible facade (issue #81, #343).

Any client that speaks the native Ollama API — JetBrains AI Assistant,
ChatGPT Desktop, Zed, Continue, etc. — can point at daari as if it were an
Ollama server and get the full router (caching, tiering, escalation) underneath.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict

from daari.gateway.client_errors import backend_unavailable_message, request_deadline_response, routing_failure_detail, safe_detail
from daari.gateway.base import GatewayAdapter
from daari.gateway.content import content_to_text, extract_images
from daari.gateway.embeddings_api import (
    compute_embeddings,
    embedding_texts,
    resolve_embedding_model,
)
from daari.gateway.internal import ContentImage, InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.gateway.disconnect import ClientDisconnected, await_unless_disconnected, note_request_cancelled
from daari.gateway.streaming import NDJSON_KEEPALIVE_FRAME, stream_with_keepalive
from daari.router.capabilities import UnsupportedCapability
from daari.router.local_pool import BackendUnavailable
from daari.router.router import AppContext

DEFAULT_CLIENT_ID = "ollama-compat"


class OllamaChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str | list[dict[str, Any]] | None = None
    images: list[str] | None = None


class OllamaChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[OllamaChatMessage]
    # Native Ollama defaults to streaming NDJSON.
    stream: bool = True
    options: dict[str, Any] | None = None


class OllamaGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "daari"
    prompt: str = ""
    system: str | None = None
    images: list[str] | None = None
    stream: bool = True
    options: dict[str, Any] | None = None
    format: Any | None = None


class OllamaEmbedRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "daari"
    input: str | list[str] = ""


class OllamaEmbeddingsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "daari"
    prompt: str = ""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _model_entry(name: str, *, capabilities: list[str] | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": name,
        "model": name,
        "modified_at": _now_iso(),
        "size": 0,
        "digest": "daari-virtual",
        "details": {
            "format": "daari",
            "family": "daari",
            "parameter_size": "routed",
            "quantization_level": "none",
        },
    }
    if capabilities is not None:
        entry["capabilities"] = list(capabilities)
    return entry


def _chat_line(
    model: str,
    content: str,
    *,
    done: bool,
    done_reason: str | None = None,
    usage: tuple[int, int] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "created_at": _now_iso(),
        "message": {"role": "assistant", "content": content},
        "done": done,
    }
    if done:
        prompt_tokens, completion_tokens = usage if usage is not None else (0, 0)
        payload["done_reason"] = done_reason or "stop"
        payload.update(
            {
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": prompt_tokens,
                "eval_count": completion_tokens,
            }
        )
    return json.dumps(payload) + "\n"


def _generate_line(
    model: str,
    content: str,
    *,
    done: bool,
    done_reason: str | None = None,
    usage: tuple[int, int] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "created_at": _now_iso(),
        "response": content,
        "done": done,
    }
    if done:
        prompt_tokens, completion_tokens = usage if usage is not None else (0, 0)
        payload["done_reason"] = done_reason or "stop"
        payload.update(
            {
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": prompt_tokens,
                "eval_count": completion_tokens,
            }
        )
    return json.dumps(payload) + "\n"


def _extract_content_deltas(sse_chunk: str) -> tuple[list[str], bool, tuple[int, int] | None]:
    """Pull assistant content deltas, the [DONE] marker, and any usage report
    out of an OpenAI-style SSE chunk string."""
    deltas: list[str] = []
    done = False
    usage: tuple[int, int] | None = None
    for line in sse_chunk.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[len("data:") :].strip()
        if data == "[DONE]":
            done = True
            continue
        try:
            parsed = json.loads(data)
        except json.JSONDecodeError:
            continue
        for choice in parsed.get("choices", []):
            content = (choice.get("delta") or {}).get("content")
            if isinstance(content, str) and content:
                deltas.append(content)
        reported = parsed.get("usage")
        if isinstance(reported, dict):
            usage = (
                int(reported.get("prompt_tokens") or 0),
                int(reported.get("completion_tokens") or 0),
            )
    return deltas, done, usage


def _temperature_from_options(options: dict[str, Any] | None) -> float:
    if options and isinstance(options.get("temperature"), (int, float)):
        return float(options["temperature"])
    return 0.7


def _resolve_model(client_model: str, ctx: AppContext) -> str:
    return client_model if client_model != "daari" else ctx.settings.models.l3


def _enforce_ollama_model(request: Request, ctx: AppContext, meta: RequestMeta, *models: str):
    """Bind virtual-key allowlists and 403 if any candidate model is outside them."""
    from daari.gateway.model_access import reject_disallowed_model
    from daari.server.auth import apply_auth_claims_to_meta

    apply_auth_claims_to_meta(
        meta,
        getattr(request.state, "auth_claims", None),
        model_groups=getattr(ctx.settings, "model_groups", None),
    )
    seen: set[str] = set()
    for model in models:
        name = (model or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        denied = reject_disallowed_model(request, name, ctx.settings, meta)
        if denied is not None:
            return denied
    return None


class OllamaCompatGatewayAdapter(GatewayAdapter):
    id = "ollama-compat"

    def router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/api/version")
        async def version() -> dict[str, str]:
            # Recent-enough version string so clients don't demand upgrades.
            return {"version": "0.5.0", "daari": "ollama-compat-facade"}

        @router.get("/api/tags")
        async def tags(request: Request) -> dict[str, Any]:
            from daari.router.capabilities import ollama_facade_capabilities_for_name

            ctx: AppContext = request.app.state.ctx
            names = ["daari", ctx.settings.models.l3, ctx.settings.models.l4, ctx.settings.models.l5]
            unique: list[str] = []
            for name in names:
                if name and name not in unique:
                    unique.append(name)
            return {
                "models": [
                    _model_entry(
                        name,
                        capabilities=ollama_facade_capabilities_for_name(name, ctx.settings),
                    )
                    for name in unique
                ]
            }

        @router.post("/api/show")
        async def show(request: Request, body: dict[str, Any]) -> dict[str, Any]:
            from daari.gateway.sampling import ollama_thinking_controls
            from daari.router.capabilities import ollama_facade_capabilities_for_name

            ctx: AppContext = request.app.state.ctx
            name = str(body.get("model") or body.get("name") or "daari")
            caps = ollama_facade_capabilities_for_name(name, ctx.settings)
            entry = _model_entry(name, capabilities=caps)
            payload: dict[str, Any] = {
                "modelfile": f"# daari virtual model: {name}",
                "parameters": "",
                "template": "",
                "details": entry["details"],
                "model_info": {"general.architecture": "daari-router"},
                "capabilities": caps,
            }
            # Ollama ≥0.34.3 advertises think levels only on show (#789).
            if "thinking" in caps:
                payload["thinking"] = ollama_thinking_controls()
            return payload

        async def _stream_ndjson(
            ctx: AppContext,
            internal: InternalRequest,
            client_model: str,
            *,
            line_fn,
        ) -> StreamingResponse:
            async def ndjson_stream() -> AsyncIterator[str]:
                # The router emits its usage chunk right before [DONE]; the
                # last report wins so the final NDJSON line carries the
                # provider's real counts (#320).
                usage: tuple[int, int] | None = None
                try:
                    async for sse_chunk in stream_with_keepalive(
                        ctx.router.stream_openai_chunks(internal),
                        interval_seconds=ctx.settings.server.sse_keepalive_seconds,
                        frame=NDJSON_KEEPALIVE_FRAME,
                        on_cancel=lambda: note_request_cancelled(
                            ctx.metrics, "stream", model=client_model
                        ),
                    ):
                        if sse_chunk == NDJSON_KEEPALIVE_FRAME:
                            yield sse_chunk
                            continue
                        deltas, done, reported = _extract_content_deltas(sse_chunk)
                        if reported is not None:
                            usage = reported
                        for delta in deltas:
                            yield line_fn(client_model, delta, done=False)
                        if done:
                            yield line_fn(client_model, "", done=True, usage=usage)
                except Exception as exc:
                    yield json.dumps({"error": safe_detail(exc), "done": True}) + "\n"

            return StreamingResponse(ndjson_stream(), media_type="application/x-ndjson")

        async def _route_non_stream(
            ctx: AppContext, internal: InternalRequest, request: Request
        ) -> Any:
            try:
                return await await_unless_disconnected(
                    request,
                    ctx.router.route(internal),
                    metrics=ctx.metrics,
                    phase="chat",
                    model=internal.model,
                )
            except ClientDisconnected:
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
                raise HTTPException(status_code=422, detail=safe_detail(exc)) from exc
            except BackendUnavailable as exc:
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
            except Exception as exc:
                from daari.router.deadline import RequestDeadlineExceeded

                if isinstance(exc, RequestDeadlineExceeded):
                    return request_deadline_response(exc)
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=routing_failure_detail(exc)) from exc

        @router.post("/api/chat", response_model=None)
        async def chat(
            body: OllamaChatRequest,
            request: Request,
            x_daari_client_id: str | None = Header(default=None, alias="X-Daari-Client-Id"),
            x_daari_deadline_ms: str | None = Header(default=None, alias="X-Daari-Deadline-Ms"),
        ) -> Any:
            from daari.router.deadline import (
                RequestDeadlineExceeded,
                bind_request_deadline,
                guard_upstream,
                parse_deadline_ms,
                resolve_deadline_seconds,
            )

            ctx: AppContext = request.app.state.ctx
            client_model = body.model or "daari"
            deadline_ms = parse_deadline_ms(x_daari_deadline_ms)
            internal = InternalRequest(
                messages=[
                    Message(
                        role=message.role,
                        content=content_to_text(message.content),
                        images=(
                            extract_images(message.content)
                            + [
                                ContentImage(data=item)
                                for item in (message.images or [])
                                if item
                            ]
                        ),
                    )
                    for message in body.messages
                ],
                model=_resolve_model(client_model, ctx),
                temperature=_temperature_from_options(body.options),
                stream=body.stream,
                meta=RequestMeta(
                    client_id=(x_daari_client_id or DEFAULT_CLIENT_ID).strip(),
                    deadline_ms=deadline_ms,
                ),
                sampling=SamplingParams.from_ollama_options(body.options),
            )
            denied = _enforce_ollama_model(
                request, ctx, internal.meta, client_model, internal.model
            )
            if denied is not None:
                return denied

            if body.stream:
                seconds = resolve_deadline_seconds(
                    deadline_ms,
                    getattr(ctx.settings.upstream, "request_deadline_seconds", None),
                )
                if seconds is not None and seconds <= 0:
                    try:
                        with bind_request_deadline(seconds, metrics=ctx.metrics):
                            guard_upstream("stream")
                    except RequestDeadlineExceeded as exc:
                        return request_deadline_response(exc)
                return await _stream_ndjson(ctx, internal, client_model, line_fn=_chat_line)

            result = await _route_non_stream(ctx, internal, request)
            if isinstance(result, JSONResponse):
                return result
            payload = json.loads(_chat_line(client_model, result.content, done=True))
            payload["daari_meta"] = result.daari_meta.model_dump(exclude_none=True)
            return payload

        @router.post("/api/generate", response_model=None)
        async def generate(
            body: OllamaGenerateRequest,
            request: Request,
            x_daari_client_id: str | None = Header(default=None, alias="X-Daari-Client-Id"),
            x_daari_deadline_ms: str | None = Header(default=None, alias="X-Daari-Deadline-Ms"),
        ) -> Any:
            from daari.router.deadline import (
                RequestDeadlineExceeded,
                bind_request_deadline,
                guard_upstream,
                parse_deadline_ms,
                resolve_deadline_seconds,
            )

            ctx: AppContext = request.app.state.ctx
            client_model = body.model or "daari"
            deadline_ms = parse_deadline_ms(x_daari_deadline_ms)
            messages: list[Message] = []
            if body.system:
                messages.append(Message(role="system", content=body.system))
            messages.append(
                Message(
                    role="user",
                    content=body.prompt,
                    images=[
                        ContentImage(data=item) for item in (body.images or []) if item
                    ],
                )
            )
            options = dict(body.options or {})
            if body.format is not None and "format" not in options:
                options["format"] = body.format
            internal = InternalRequest(
                messages=messages,
                model=_resolve_model(client_model, ctx),
                temperature=_temperature_from_options(body.options),
                stream=body.stream,
                meta=RequestMeta(
                    client_id=(x_daari_client_id or DEFAULT_CLIENT_ID).strip(),
                    deadline_ms=deadline_ms,
                ),
                sampling=SamplingParams.from_ollama_options(options or None),
            )
            denied = _enforce_ollama_model(
                request, ctx, internal.meta, client_model, internal.model
            )
            if denied is not None:
                return denied

            if body.stream:
                seconds = resolve_deadline_seconds(
                    deadline_ms,
                    getattr(ctx.settings.upstream, "request_deadline_seconds", None),
                )
                if seconds is not None and seconds <= 0:
                    try:
                        with bind_request_deadline(seconds, metrics=ctx.metrics):
                            guard_upstream("stream")
                    except RequestDeadlineExceeded as exc:
                        return request_deadline_response(exc)
                return await _stream_ndjson(ctx, internal, client_model, line_fn=_generate_line)

            result = await _route_non_stream(ctx, internal, request)
            if isinstance(result, JSONResponse):
                return result
            payload = json.loads(_generate_line(client_model, result.content, done=True))
            payload["daari_meta"] = result.daari_meta.model_dump(exclude_none=True)
            return payload

        @router.post("/api/embed")
        async def embed(body: OllamaEmbedRequest, request: Request) -> Any:
            ctx: AppContext = request.app.state.ctx
            from daari.gateway.internal import RequestMeta

            meta = RequestMeta()
            denied = _enforce_ollama_model(request, ctx, meta, body.model or "daari")
            if denied is not None:
                return denied
            model = resolve_embedding_model(ctx, body.model)
            texts = embedding_texts(body.input)
            try:
                vectors = await await_unless_disconnected(
                    request,
                    compute_embeddings(ctx, texts, model=model, request=request),
                    metrics=ctx.metrics,
                    phase="embed",
                    model=model,
                )
            except ClientDisconnected:
                return JSONResponse(
                    status_code=499,
                    content={
                        "error": {
                            "type": "client_disconnected",
                            "message": "client disconnected.",
                        }
                    },
                )
            return {"model": model, "embeddings": vectors}

        @router.post("/api/embeddings")
        async def embeddings(body: OllamaEmbeddingsRequest, request: Request) -> Any:
            ctx: AppContext = request.app.state.ctx
            from daari.gateway.internal import RequestMeta

            meta = RequestMeta()
            denied = _enforce_ollama_model(request, ctx, meta, body.model or "daari")
            if denied is not None:
                return denied
            model = resolve_embedding_model(ctx, body.model)
            texts = embedding_texts(body.prompt)
            try:
                vectors = await await_unless_disconnected(
                    request,
                    compute_embeddings(ctx, texts, model=model, request=request),
                    metrics=ctx.metrics,
                    phase="embed",
                    model=model,
                )
            except ClientDisconnected:
                return JSONResponse(
                    status_code=499,
                    content={
                        "error": {
                            "type": "client_disconnected",
                            "message": "client disconnected.",
                        }
                    },
                )
            return {"embedding": vectors[0] if vectors else []}

        @router.get("/api/ps")
        async def ps() -> dict[str, Any]:
            return {"models": []}

        return router

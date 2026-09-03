"""Ollama-compatible facade (issue #81).

Any client that speaks the native Ollama API — JetBrains AI Assistant,
Zed, Continue, etc. — can point at daari as if it were an Ollama server
and get the full router (caching, tiering, escalation) underneath.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from daari.gateway.base import GatewayAdapter
from daari.gateway.content import content_to_text, extract_images
from daari.gateway.internal import ContentImage, InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.gateway.streaming import NDJSON_KEEPALIVE_FRAME, stream_with_keepalive
from daari.router.capabilities import UnsupportedCapability
from daari.router.local_pool import BackendUnavailable
from daari.router.router import AppContext

DEFAULT_CLIENT_ID = "ollama-compat"


class OllamaChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None
    images: list[str] | None = None


class OllamaChatRequest(BaseModel):
    model: str
    messages: list[OllamaChatMessage]
    # Native Ollama defaults to streaming NDJSON.
    stream: bool = True
    options: dict[str, Any] | None = None


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _model_entry(name: str) -> dict[str, Any]:
    return {
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
            ctx: AppContext = request.app.state.ctx
            names = ["daari", ctx.settings.models.l3, ctx.settings.models.l4, ctx.settings.models.l5]
            unique: list[str] = []
            for name in names:
                if name and name not in unique:
                    unique.append(name)
            return {"models": [_model_entry(name) for name in unique]}

        @router.post("/api/show")
        async def show(body: dict[str, Any]) -> dict[str, Any]:
            name = str(body.get("model") or body.get("name") or "daari")
            entry = _model_entry(name)
            return {
                "modelfile": f"# daari virtual model: {name}",
                "parameters": "",
                "template": "",
                "details": entry["details"],
                "model_info": {"general.architecture": "daari-router"},
                "capabilities": ["completion"],
            }

        @router.post("/api/chat", response_model=None)
        async def chat(
            body: OllamaChatRequest,
            request: Request,
            x_daari_client_id: str | None = Header(default=None, alias="X-Daari-Client-Id"),
        ) -> Any:
            ctx: AppContext = request.app.state.ctx
            client_model = body.model or "daari"
            temperature = 0.7
            if body.options and isinstance(body.options.get("temperature"), (int, float)):
                temperature = float(body.options["temperature"])

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
                model=client_model if client_model != "daari" else ctx.settings.models.l3,
                temperature=temperature,
                stream=body.stream,
                meta=RequestMeta(client_id=(x_daari_client_id or DEFAULT_CLIENT_ID).strip()),
                sampling=SamplingParams.from_ollama_options(body.options),
            )

            if body.stream:

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
                        ):
                            if sse_chunk == NDJSON_KEEPALIVE_FRAME:
                                yield sse_chunk
                                continue
                            deltas, done, reported = _extract_content_deltas(sse_chunk)
                            if reported is not None:
                                usage = reported
                            for delta in deltas:
                                yield _chat_line(client_model, delta, done=False)
                            if done:
                                yield _chat_line(client_model, "", done=True, usage=usage)
                    except Exception as exc:
                        yield json.dumps({"error": str(exc), "done": True}) + "\n"

                return StreamingResponse(ndjson_stream(), media_type="application/x-ndjson")

            try:
                result = await ctx.router.route(internal)
            except UnsupportedCapability as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            except BackendUnavailable as exc:
                ctx.metrics.record_error()
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "type": "backend_unavailable",
                            "message": str(exc),
                        }
                    },
                )
            except Exception as exc:
                ctx.metrics.record_error()
                raise HTTPException(status_code=503, detail=f"Routing failed: {exc}") from exc

            payload = json.loads(_chat_line(client_model, result.content, done=True))
            payload["daari_meta"] = result.daari_meta.model_dump(exclude_none=True)
            return payload

        @router.get("/api/ps")
        async def ps() -> dict[str, Any]:
            return {"models": []}

        return router

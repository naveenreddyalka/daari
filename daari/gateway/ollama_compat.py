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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from daari.gateway.base import GatewayAdapter
from daari.gateway.content import content_to_text
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.router.router import AppContext

DEFAULT_CLIENT_ID = "ollama-compat"


class OllamaChatMessage(BaseModel):
    role: str
    content: str | list[dict[str, Any]] | None = None


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


def _chat_line(model: str, content: str, *, done: bool, done_reason: str | None = None) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "created_at": _now_iso(),
        "message": {"role": "assistant", "content": content},
        "done": done,
    }
    if done:
        payload["done_reason"] = done_reason or "stop"
        payload.update(
            {
                "total_duration": 0,
                "load_duration": 0,
                "prompt_eval_count": 0,
                "eval_count": 0,
            }
        )
    return json.dumps(payload) + "\n"


def _extract_content_deltas(sse_chunk: str) -> tuple[list[str], bool]:
    """Pull assistant content deltas out of an OpenAI-style SSE chunk string."""
    deltas: list[str] = []
    done = False
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
    return deltas, done


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
                    Message(role=message.role, content=content_to_text(message.content))
                    for message in body.messages
                ],
                model=client_model if client_model != "daari" else ctx.settings.models.l3,
                temperature=temperature,
                stream=body.stream,
                meta=RequestMeta(client_id=(x_daari_client_id or DEFAULT_CLIENT_ID).strip()),
            )

            if body.stream:

                async def ndjson_stream() -> AsyncIterator[str]:
                    try:
                        async for sse_chunk in ctx.router.stream_openai_chunks(internal):
                            deltas, done = _extract_content_deltas(sse_chunk)
                            for delta in deltas:
                                yield _chat_line(client_model, delta, done=False)
                            if done:
                                yield _chat_line(client_model, "", done=True)
                    except Exception as exc:
                        yield json.dumps({"error": str(exc), "done": True}) + "\n"

                return StreamingResponse(ndjson_stream(), media_type="application/x-ndjson")

            try:
                result = await ctx.router.route(internal)
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

"""MLX backend executor (issue #97, roadmap C2).

Talks to an `mlx_lm.server` instance over its OpenAI-compatible API while
duck-typing OllamaExecutor: same execute/stream contract, and stream events
are converted to Ollama's shape so the router tier loops work unchanged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse


class MLXRequestError(RuntimeError):
    """HTTP error from mlx_lm.server with the response body preserved."""

    def __init__(self, status_code: int, url: str, body: str):
        self.status_code = status_code
        self.url = url
        self.body = body[:2000]
        super().__init__(f"mlx_lm.server returned {status_code} for {url}: {self.body}")


@dataclass
class MLXExecutor:
    base_url: str
    default_model: str
    tier: str = "L3"
    timeout: float = 120.0

    def _payload(self, request: InternalRequest, model: str, *, stream: bool) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for m in request.messages:
            data = m.model_dump(exclude_none=True)
            tool_calls = data.get("tool_calls")
            if tool_calls:
                # OpenAI wire format wants function.arguments as a JSON string;
                # internal history may carry objects (Ollama shape).
                for call in tool_calls:
                    function = call.get("function") if isinstance(call, dict) else None
                    if isinstance(function, dict) and not isinstance(
                        function.get("arguments"), str
                    ):
                        function["arguments"] = json.dumps(function.get("arguments") or {})
            elif not data.get("content"):
                continue
            messages.append(data)
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": stream}
        if request.tools:
            payload["tools"] = request.tools
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        return payload

    def _meta(self, model: str, latency_ms: int) -> DaariMeta:
        return DaariMeta(
            tier=self.tier,
            cache_hit=False,
            executor="mlx",
            provider_id=f"mlx:{self.tier.lower()}",
            latency_ms=latency_ms,
            model=model,
        )

    async def execute(self, request: InternalRequest) -> InternalResponse:
        model = request.model or self.default_model
        started = time.perf_counter()
        payload = self._payload(request, model, stream=False)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/v1/chat/completions", json=payload)
            if response.status_code >= 400:
                raise MLXRequestError(
                    response.status_code, str(response.request.url), response.text
                )
            data = response.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        latency_ms = int((time.perf_counter() - started) * 1000)
        return InternalResponse(
            content=content, model=model, daari_meta=self._meta(model, latency_ms)
        )

    async def stream(self, request: InternalRequest) -> AsyncIterator[dict]:
        """Yield Ollama-style events converted from OpenAI SSE chunks."""
        model = request.model or self.default_model
        payload = self._payload(request, model, stream=True)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise MLXRequestError(response.status_code, str(response.request.url), body)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        yield {"message": {"role": "assistant", "content": ""}, "done": True}
                        return
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choice = (chunk.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    message: dict[str, Any] = {
                        "role": "assistant",
                        "content": delta.get("content") or "",
                    }
                    if delta.get("tool_calls"):
                        message["tool_calls"] = delta["tool_calls"]
                    yield {"message": message, "done": False}
        yield {"message": {"role": "assistant", "content": ""}, "done": True}

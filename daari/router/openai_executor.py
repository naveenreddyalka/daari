"""OpenAI-compatible local executor (vLLM, llama.cpp server, LM Studio) — #275.

Duck-types OllamaExecutor: same execute/stream contract, and stream events
are converted to Ollama's shape so the router tier loops work unchanged.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.retry import RetryPolicy, run_upstream


class OpenAICompatRequestError(RuntimeError):
    """HTTP error from an OpenAI-compat local server with the body preserved."""

    def __init__(self, status_code: int, url: str, body: str):
        self.status_code = status_code
        self.url = url
        self.body = body[:2000]
        super().__init__(f"openai-compat returned {status_code} for {url}: {self.body}")


@dataclass
class OpenAICompatExecutor:
    base_url: str
    default_model: str
    tier: str = "L3"
    timeout: float = 120.0
    retry: RetryPolicy | None = None
    metrics: Any = None

    def _payload(self, request: InternalRequest, model: str, *, stream: bool) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for m in request.messages:
            data = m.model_dump(exclude_none=True, exclude={"images"})
            tool_calls = data.get("tool_calls")
            if m.images:
                parts: list[dict[str, Any]] = []
                if data.get("content"):
                    parts.append({"type": "text", "text": data["content"]})
                for image in m.images:
                    url = image.as_data_url()
                    if url:
                        parts.append({"type": "image_url", "image_url": {"url": url}})
                if parts:
                    data["content"] = parts
            if tool_calls:
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
        if stream:
            # vLLM / llama.cpp / LM Studio only send token counts on a stream
            # when asked; without this the ledger falls back to chars/4 (#320).
            payload["stream_options"] = {"include_usage": True}
        if request.tools:
            payload["tools"] = request.tools
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        payload.update(request.sampling.openai_payload())
        return payload

    def _meta(self, model: str, latency_ms: int) -> DaariMeta:
        return DaariMeta(
            tier=self.tier,
            cache_hit=False,
            executor="openai",
            provider_id=f"openai:{self.tier.lower()}",
            latency_ms=latency_ms,
            model=model,
        )

    async def execute(self, request: InternalRequest) -> InternalResponse:
        model = request.model or self.default_model
        started = time.perf_counter()
        payload = self._payload(request, model, stream=False)

        async def attempt() -> dict[str, Any]:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout
            ) as client:
                response = await client.post("/v1/chat/completions", json=payload)
                if response.status_code >= 400:
                    raise OpenAICompatRequestError(
                        response.status_code, str(response.request.url), response.text
                    )
                return response.json()

        data = await run_upstream(
            attempt,
            upstream=f"openai:{self.tier}",
            policy=self.retry,
            timeout=self.timeout,
            metrics=self.metrics,
        )
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        tool_calls = message.get("tool_calls") or None
        latency_ms = int((time.perf_counter() - started) * 1000)
        return InternalResponse(
            content=content,
            model=model,
            finish_reason="tool_calls" if tool_calls else (choice.get("finish_reason") or "stop"),
            tool_calls=tool_calls,
            daari_meta=self._meta(model, latency_ms),
        )

    async def stream(self, request: InternalRequest) -> AsyncIterator[dict]:
        """Yield Ollama-style events converted from OpenAI SSE chunks."""
        model = request.model or self.default_model
        payload = self._payload(request, model, stream=True)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            async with client.stream("POST", "/v1/chat/completions", json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise OpenAICompatRequestError(
                        response.status_code, str(response.request.url), body
                    )
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
                    event: dict[str, Any] = {"message": message, "done": False}
                    # Whether the backend sends one usage-only chunk before
                    # [DONE] or running totals on every chunk, each report is
                    # passed through as-is; the router keeps the last one.
                    usage = chunk.get("usage")
                    if isinstance(usage, dict):
                        event["prompt_eval_count"] = int(usage.get("prompt_tokens") or 0)
                        event["eval_count"] = int(usage.get("completion_tokens") or 0)
                    yield event
        yield {"message": {"role": "assistant", "content": ""}, "done": True}

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.tokens import openai_token_usage
from daari.observability.trace import add_step
from daari.router.retry import RetryPolicy, run_upstream


@dataclass
class FrontierExecutor:
    base_url: str
    default_model: str
    api_key: str | None = None
    provider: str = "openai"
    timeout: float = 120.0
    # Trust PRD T2a: mark the stable system prefix for provider-side prompt
    # caching. Anthropic needs explicit cache_control; OpenAI caches stable
    # prefixes automatically, so no payload change is needed there.
    prompt_cache: bool = True
    transport: httpx.AsyncBaseTransport | None = None
    retry: RetryPolicy | None = None
    metrics: Any = None

    def _build_messages(self, request: InternalRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            entry: dict[str, Any] = {"role": message.role}
            if message.tool_calls:
                entry["tool_calls"] = message.tool_calls
            if message.images:
                parts: list[dict[str, Any]] = []
                if message.content:
                    parts.append({"type": "text", "text": message.content})
                for image in message.images:
                    url = image.as_data_url()
                    if url:
                        parts.append({"type": "image_url", "image_url": {"url": url}})
                entry["content"] = parts
            elif message.content is not None:
                entry["content"] = message.content
            messages.append(entry)
        if self.provider != "anthropic" or not self.prompt_cache:
            return messages
        marked = 0
        for message in messages:
            if message.get("role") != "system":
                break
            content = message.get("content")
            if isinstance(content, str) and content:
                message["content"] = [
                    {
                        "type": "text",
                        "text": content,
                        "cache_control": {"type": "ephemeral"},
                    }
                ]
                marked += 1
        if marked:
            add_step("prompt_cache_hint", provider=self.provider, marked_blocks=marked)
        return messages

    async def stream(
        self,
        request: InternalRequest,
        *,
        escalated_from: str | None = None,
        local_confidence: float | None = None,
    ) -> AsyncIterator[str]:
        """Relay upstream SSE as text deltas.

        Lets an escalated stream reach the client incrementally instead of
        waiting for the whole frontier answer to buffer (#155).
        """
        if not self.api_key:
            raise RuntimeError("frontier API key not configured")

        payload = {
            "model": self.default_model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "stream": True,
            **request.sampling.openai_payload(),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            async with client.stream(
                "POST", "/chat/completions", json=payload, headers=headers
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    for choice in chunk.get("choices", []):
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            yield delta

    async def execute(
        self,
        request: InternalRequest,
        *,
        escalated_from: str,
        local_confidence: float,
    ) -> InternalResponse:
        if not self.api_key:
            raise RuntimeError("frontier API key not configured")

        model = self.default_model
        started = time.perf_counter()
        payload = {
            "model": model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "stream": False,
            **request.sampling.openai_payload(),
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}

        async def attempt() -> dict[str, Any]:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self.timeout, transport=self.transport
            ) as client:
                response = await client.post(
                    "/chat/completions", json=payload, headers=headers
                )
                response.raise_for_status()
                return response.json()

        data = await run_upstream(
            attempt,
            upstream=f"frontier:{self.provider}",
            policy=self.retry,
            timeout=self.timeout,
            metrics=self.metrics,
        )
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        latency_ms = int((time.perf_counter() - started) * 1000)
        prompt_chars = sum(len(message.content or "") for message in request.messages)
        input_tokens, output_tokens, estimated = openai_token_usage(data, prompt_chars, content)
        return InternalResponse(
            content=content,
            model=model,
            daari_meta=DaariMeta(
                tier="L6",
                cache_hit=False,
                executor="frontier",
                provider_id=self.provider,
                latency_ms=latency_ms,
                model=model,
                confidence=local_confidence,
                escalated_from=escalated_from,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                usage_estimated=estimated,
            ),
        )

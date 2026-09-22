from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.provider_prefs import (
    as_openrouter_payload,
    is_openrouter_base,
    usage_cost_and_cache,
)
from daari.observability.tokens import openai_token_usage
from daari.router.anthropic_messages import (
    anthropic_headers_for_request,
    anthropic_messages_path,
    infer_frontier_kind,
    text_delta_from_sse_data,
    text_from_anthropic_content,
    to_anthropic_payload,
)
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
    pool_limits: Any = None
    _http: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or getattr(self._http, "is_closed", False):
            from daari.router.http_pool import PoolLimits, build_async_client

            self._http = build_async_client(
                httpx,
                base_url=self.base_url,
                limits=self.pool_limits or PoolLimits(),
                transport=self.transport,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None and not getattr(self._http, "is_closed", True):
            await self._http.aclose()
        self._http = None

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
        return messages

    def _is_anthropic(self) -> bool:
        return infer_frontier_kind(self.provider, self.base_url) == "anthropic"

    def _openai_payload(self, request: InternalRequest, *, stream: bool) -> dict[str, Any]:
        payload = {
            "model": self.default_model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "stream": stream,
            **request.sampling.openai_payload(),
        }
        if request.provider is not None and (
            self.provider == "openrouter" or is_openrouter_base(self.base_url)
        ):
            payload["provider"] = as_openrouter_payload(request.provider)
        return payload

    def _openai_headers(self) -> dict[str, str]:
        from daari.observability.otel import inject_trace_headers

        if self.provider == "openrouter" or is_openrouter_base(self.base_url):
            from daari.router.openrouter import openrouter_headers

            return inject_trace_headers(openrouter_headers(self.api_key or ""))
        return inject_trace_headers({"Authorization": f"Bearer {self.api_key}"})

    async def stream(
        self,
        request: InternalRequest,
        *,
        escalated_from: str | None = None,
        local_confidence: float | None = None,
    ) -> AsyncIterator[str]:
        """Relay upstream SSE as text deltas.

        Lets an escalated stream reach the client incrementally instead of
        waiting for the whole frontier answer to buffer (#155). Anthropic
        upstream is parsed from native SSE, not an OpenAI body (#166).
        """
        if not self.api_key:
            raise RuntimeError("frontier API key not configured")

        if self._is_anthropic():
            payload = to_anthropic_payload(
                request,
                model=self.default_model,
                stream=True,
                prompt_cache=self.prompt_cache,
            )
            from daari.observability.otel import inject_trace_headers

            headers = inject_trace_headers(
                anthropic_headers_for_request(self.api_key, request)
            )
            path = anthropic_messages_path(self.base_url)
        else:
            payload = self._openai_payload(request, stream=True)
            headers = self._openai_headers()
            path = "/chat/completions"

        from daari.router.deadline import (
            aiter_with_ttft_deadline,
            deadline_bounded_stream,
            guard_upstream,
        )

        guard_upstream("L6")
        async with deadline_bounded_stream(
            self._client(),
            "POST",
            path,
            json=payload,
            headers=headers,
            timeout=self.timeout,
        ) as response:
            response.raise_for_status()
            async for line in aiter_with_ttft_deadline(response.aiter_lines()):
                if self._is_anthropic():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    delta = text_delta_from_sse_data(data) if data else None
                    if delta:
                        yield delta
                    continue
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
        anthropic = self._is_anthropic()
        if anthropic:
            payload = to_anthropic_payload(
                request,
                model=model,
                stream=False,
                prompt_cache=self.prompt_cache,
            )
            from daari.observability.otel import inject_trace_headers

            headers = inject_trace_headers(
                anthropic_headers_for_request(self.api_key, request)
            )
            path = anthropic_messages_path(self.base_url)
        else:
            payload = self._openai_payload(request, stream=False)
            headers = self._openai_headers()
            path = "/chat/completions"

        from daari.router.deadline import nonstream_timeout

        timeout = nonstream_timeout(self.timeout, "L6")

        async def attempt() -> dict[str, Any]:
            response = await self._client().post(
                path, json=payload, headers=headers, timeout=timeout
            )
            response.raise_for_status()
            return response.json()

        data = await run_upstream(
            attempt,
            upstream=f"frontier:{self.provider}",
            policy=self.retry,
            timeout=timeout,
            metrics=self.metrics,
        )
        if anthropic:
            content = text_from_anthropic_content(data.get("content"))
        else:
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        latency_ms = int((time.perf_counter() - started) * 1000)
        prompt_chars = sum(len(message.content or "") for message in request.messages)
        input_tokens, output_tokens, estimated = openai_token_usage(
            data, prompt_chars, content
        )
        cost_usd, cached_tokens = usage_cost_and_cache(data)
        provider_prefs = (
            as_openrouter_payload(request.provider) if request.provider is not None else None
        )
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
                cost_usd=cost_usd,
                cached_tokens=cached_tokens,
                provider_prefs=provider_prefs,
                daari_cost_usd=0.0,
                service_tier=request.sampling.service_tier,
            ),
        )

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
    anthropic_tool_event_from_sse_data,
    infer_frontier_kind,
    text_delta_from_sse_data,
    text_from_anthropic_content,
    to_anthropic_payload,
)
from daari.router.param_compat import (
    FrontierParamCompatResult,
    apply_frontier_param_compat,
)
from daari.router.retry import RetryPolicy, run_upstream


# Stream events: plain str for text, or a dict tagged for tool-call relay (#934).
FrontierStreamEvent = str | dict[str, Any]


def _tool_calls_from_anthropic_content(content: Any) -> list[dict[str, Any]] | None:
    """Convert Anthropic tool_use blocks to OpenAI-shaped tool_calls."""
    if not isinstance(content, list):
        return None
    calls: list[dict[str, Any]] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        arguments = block.get("input")
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments or {})
        calls.append(
            {
                "id": block.get("id") or f"call_{len(calls)}",
                "type": "function",
                "function": {
                    "name": block.get("name") or "",
                    "arguments": arguments,
                },
            }
        )
    return calls or None


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
    last_param_compat: FrontierParamCompatResult | None = field(
        default=None, init=False, repr=False
    )

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
            if message.images or message.audio:
                parts: list[dict[str, Any]] = []
                if message.content:
                    parts.append({"type": "text", "text": message.content})
                for image in message.images:
                    url = image.as_data_url()
                    if url:
                        parts.append({"type": "image_url", "image_url": {"url": url}})
                for clip in message.audio:
                    parts.append(clip.as_openai_part())
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
        # Stream and non-stream must both forward tools (#1006). tool_choice
        # already arrives via sampling.openai_payload().
        if request.tools:
            payload["tools"] = request.tools
        if request.provider is not None and (
            self.provider == "openrouter" or is_openrouter_base(self.base_url)
        ):
            payload["provider"] = as_openrouter_payload(request.provider)
        # Model-aware sanitation for frontier ids that reject sampler knobs (#1129).
        compat = apply_frontier_param_compat(
            payload,
            self.default_model,
            has_tools=bool(request.tools),
        )
        self.last_param_compat = compat
        if compat.tools_transport_warned:
            from daari.gateway.request_log import log_gateway_event

            log_gateway_event(
                "frontier.tools_transport",
                {
                    "model": self.default_model,
                    "transport": "responses",
                    "path": "/chat/completions",
                },
            )
        return payload

    def _apply_param_compat_meta(self, meta: DaariMeta) -> None:
        """Attach dropped/coerced frontier param notes to daari_meta (#1129)."""
        compat = self.last_param_compat
        if compat is None:
            return
        if compat.dropped_params:
            existing = list(meta.dropped_params or [])
            for name in compat.dropped_params:
                if name not in existing:
                    existing.append(name)
            meta.dropped_params = existing
        if compat.warnings:
            notes = "; ".join(compat.warnings)
            meta.warning = f"{meta.warning}; {notes}" if meta.warning else notes

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
    ) -> AsyncIterator[FrontierStreamEvent]:
        """Relay upstream SSE as text deltas and tool-call events (#934).

        Text chunks are plain ``str``. Tool-call chunks are dicts:
        ``{"tool_calls": [...]}`` (OpenAI delta shape) or
        ``{"anthropic_event": {...}}`` (native Anthropic tool SSE payload).
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
            tool_block_open = False
            async for line in aiter_with_ttft_deadline(response.aiter_lines()):
                if self._is_anthropic():
                    if not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if not data:
                        continue
                    tool_event = anthropic_tool_event_from_sse_data(data)
                    if tool_event is not None:
                        event_type = tool_event.get("type")
                        if event_type == "content_block_start":
                            tool_block_open = True
                            yield {"anthropic_event": tool_event}
                        elif event_type == "content_block_delta":
                            yield {"anthropic_event": tool_event}
                        elif event_type == "content_block_stop" and tool_block_open:
                            tool_block_open = False
                            yield {"anthropic_event": tool_event}
                        continue
                    delta = text_delta_from_sse_data(data)
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
                    delta_obj = choice.get("delta") or {}
                    tool_calls = delta_obj.get("tool_calls")
                    if tool_calls:
                        yield {"tool_calls": tool_calls}
                    text = delta_obj.get("content")
                    if text:
                        yield text

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
            tool_calls = _tool_calls_from_anthropic_content(data.get("content"))
        else:
            message = data.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "") or ""
            tool_calls = message.get("tool_calls")
        latency_ms = int((time.perf_counter() - started) * 1000)
        prompt_chars = sum(len(message.content or "") for message in request.messages)
        input_tokens, output_tokens, estimated = openai_token_usage(
            data, prompt_chars, content
        )
        cost_usd, cached_tokens, cache_write_tokens = usage_cost_and_cache(data)
        provider_prefs = (
            as_openrouter_payload(request.provider) if request.provider is not None else None
        )
        meta = DaariMeta(
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
            cache_write_tokens=cache_write_tokens or None,
            provider_prefs=provider_prefs,
            daari_cost_usd=0.0,
            service_tier=request.sampling.service_tier,
        )
        self._apply_param_compat_meta(meta)
        return InternalResponse(
            content=content or "",
            model=model,
            tool_calls=tool_calls if tool_calls else None,
            daari_meta=meta,
        )

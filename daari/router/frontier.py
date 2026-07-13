from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.observability.trace import add_step


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

    def _build_messages(self, request: InternalRequest) -> list[dict[str, Any]]:
        messages = [m.model_dump(exclude_none=True) for m in request.messages]
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
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout, transport=self.transport
        ) as client:
            response = await client.post("/chat/completions", json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        latency_ms = int((time.perf_counter() - started) * 1000)
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
            ),
        )

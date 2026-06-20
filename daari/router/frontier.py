from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse


@dataclass
class FrontierExecutor:
    base_url: str
    default_model: str
    api_key: str | None = None
    provider: str = "openai"
    timeout: float = 120.0

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
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
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

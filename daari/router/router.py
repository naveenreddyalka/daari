from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from daari.cache.exact import ExactCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics


@dataclass
class OllamaExecutor:
    base_url: str
    default_model: str
    timeout: float = 120.0

    async def execute(self, request: InternalRequest) -> InternalResponse:
        model = request.model or self.default_model
        started = time.perf_counter()
        payload = {
            "model": model,
            "messages": [m.model_dump(exclude_none=True) for m in request.messages],
            "stream": False,
        }
        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        content = data.get("message", {}).get("content", "")
        latency_ms = int((time.perf_counter() - started) * 1000)
        return InternalResponse(
            content=content,
            model=model,
            daari_meta=DaariMeta(
                tier="L3",
                cache_hit=False,
                executor="ollama",
                provider_id="ollama",
                latency_ms=latency_ms,
                model=model,
            ),
        )


class Router:
    def __init__(
        self,
        cache: ExactCache,
        ollama: OllamaExecutor,
        metrics: Metrics,
    ) -> None:
        self.cache = cache
        self.ollama = ollama
        self.metrics = metrics

    async def route(self, request: InternalRequest) -> InternalResponse:
        started = time.perf_counter()

        if request.has_tool_calls_in_history:
            response = await self.ollama.execute(request)
            self._record(response, started)
            return response

        if not request.meta.no_cache:
            cached = self.cache.get(request)
            if cached is not None:
                latency_ms = int((time.perf_counter() - started) * 1000)
                cached.daari_meta.tier = "L0"
                cached.daari_meta.cache_hit = True
                cached.daari_meta.executor = "cache"
                cached.daari_meta.provider_id = "cache"
                cached.daari_meta.latency_ms = latency_ms
                self.metrics.record("L0", cache_hit=True, latency_ms=latency_ms)
                return cached

        response = await self.ollama.execute(request)
        if not request.meta.no_cache:
            self.cache.put(request, response)
        self._record(response, started)
        return response

    def _record(self, response: InternalResponse, started: float) -> None:
        if response.daari_meta.tier == "L0":
            return
        latency_ms = response.daari_meta.latency_ms or int((time.perf_counter() - started) * 1000)
        self.metrics.record(
            response.daari_meta.tier,
            cache_hit=response.daari_meta.cache_hit,
            latency_ms=latency_ms,
        )


@dataclass
class AppContext:
    settings: Settings
    cache: ExactCache
    ollama: OllamaExecutor
    metrics: Metrics
    router: Router

    @classmethod
    def from_settings(cls, settings: Settings) -> AppContext:
        cache = ExactCache(
            path=str(settings.l0_cache_path),
            enabled=settings.cache.l0.enabled,
        )
        ollama = OllamaExecutor(
            base_url=settings.ollama.base_url.rstrip("/"),
            default_model=settings.models.l3,
        )
        metrics = Metrics()
        router = Router(cache=cache, ollama=ollama, metrics=metrics)
        return cls(
            settings=settings,
            cache=cache,
            ollama=ollama,
            metrics=metrics,
            router=router,
        )

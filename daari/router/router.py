from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from daari.cache.exact import ExactCache
from daari.cache.semantic import OllamaEmbedder, SemanticCache
from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.confidence import score_l3_confidence
from daari.router.frontier import FrontierExecutor


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
        semantic_cache: SemanticCache,
        ollama: OllamaExecutor,
        metrics: Metrics,
        frontier: FrontierExecutor | None = None,
        *,
        frontier_enabled: bool = False,
        confidence_threshold: float = 0.7,
    ) -> None:
        self.cache = cache
        self.semantic_cache = semantic_cache
        self.ollama = ollama
        self.metrics = metrics
        self.frontier = frontier
        self.frontier_enabled = frontier_enabled
        self.confidence_threshold = confidence_threshold

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

            semantic_hit, _similarity = await self.semantic_cache.get(request)
            if semantic_hit is not None:
                latency_ms = int((time.perf_counter() - started) * 1000)
                semantic_hit.daari_meta.tier = "L1"
                semantic_hit.daari_meta.cache_hit = True
                semantic_hit.daari_meta.executor = "cache"
                semantic_hit.daari_meta.provider_id = "cache"
                semantic_hit.daari_meta.latency_ms = latency_ms
                semantic_hit.daari_meta.task_type = "cache_hit"
                self.metrics.record("L1", cache_hit=True, latency_ms=latency_ms)
                return semantic_hit

        response = await self.ollama.execute(request)
        response = await self._maybe_escalate(request, response, started)
        if not request.meta.no_cache:
            self.cache.put(request, response)
            await self.semantic_cache.put(request, response)
        self._record(response, started)
        return response

    async def _maybe_escalate(
        self,
        request: InternalRequest,
        response: InternalResponse,
        started: float,
    ) -> InternalResponse:
        confidence = score_l3_confidence(response.content)
        response.daari_meta.confidence = confidence

        if confidence >= self.confidence_threshold:
            return response

        if not self.frontier_enabled:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

        if self.frontier is None or not self.frontier.api_key:
            response.daari_meta.warning = "below_confidence_threshold"
            return response

        l6_response = await self.frontier.execute(
            request,
            escalated_from="L3",
            local_confidence=confidence,
        )
        return l6_response

    def _record(self, response: InternalResponse, started: float) -> None:
        if response.daari_meta.tier in ("L0", "L1"):
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
    semantic_cache: SemanticCache
    ollama: OllamaExecutor
    frontier: FrontierExecutor
    metrics: Metrics
    router: Router

    @classmethod
    def from_settings(cls, settings: Settings) -> AppContext:
        cache = ExactCache(
            path=str(settings.l0_cache_path),
            enabled=settings.cache.l0.enabled,
        )
        embedder = OllamaEmbedder(
            base_url=settings.ollama.base_url.rstrip("/"),
            model=settings.cache.l1.embedding_model,
        )
        semantic_cache = SemanticCache(
            path=str(settings.l1_cache_path),
            embedder=embedder,
            enabled=settings.cache.l1.enabled,
            similarity_threshold=settings.cache.l1.similarity_threshold,
            max_entries=settings.cache.l1.max_entries,
        )
        ollama = OllamaExecutor(
            base_url=settings.ollama.base_url.rstrip("/"),
            default_model=settings.models.l3,
        )
        frontier = FrontierExecutor(
            base_url=settings.frontier.base_url.rstrip("/"),
            default_model=settings.frontier.model,
            api_key=settings.resolve_frontier_api_key(),
            provider=settings.frontier.provider,
        )
        metrics = Metrics()
        router = Router(
            cache=cache,
            semantic_cache=semantic_cache,
            ollama=ollama,
            metrics=metrics,
            frontier=frontier,
            frontier_enabled=settings.frontier.enabled,
            confidence_threshold=settings.frontier.confidence_threshold,
        )
        return cls(
            settings=settings,
            cache=cache,
            semantic_cache=semantic_cache,
            ollama=ollama,
            frontier=frontier,
            metrics=metrics,
            router=router,
        )

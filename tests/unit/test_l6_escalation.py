from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.frontier import FrontierExecutor
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _semantic_cache(tmp_path) -> SemanticCache:
    return SemanticCache(
        path=str(tmp_path / "l1"),
        embedder=NoopEmbedder(),
        enabled=False,
    )


def _request(content: str = "explain routing") -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=content)],
        model="llama3.2:3b",
    )


def _l3_response(content: str) -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(
            tier="L3",
            executor="ollama",
            provider_id="ollama",
            latency_ms=5,
        ),
    )


class TestL6Escalation:
    @pytest.mark.asyncio
    async def test_escalates_on_low_confidence(self, tmp_path):
        cache = ExactCache(str(tmp_path / "c"), enabled=True)
        metrics = Metrics()
        l6_called = False

        async def fake_l3(request: InternalRequest) -> InternalResponse:
            return _l3_response("no")

        async def fake_l6(
            request: InternalRequest,
            *,
            escalated_from: str,
            local_confidence: float,
        ) -> InternalResponse:
            nonlocal l6_called
            l6_called = True
            return InternalResponse(
                content="Frontier answer with enough detail.",
                model="gpt-4o-mini",
                daari_meta=DaariMeta(
                    tier="L6",
                    executor="frontier",
                    provider_id="openai",
                    latency_ms=100,
                    model="gpt-4o-mini",
                    confidence=local_confidence,
                    escalated_from=escalated_from,
                ),
            )

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_l3  # type: ignore[method-assign]
        frontier = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key="sk-test",
        )
        frontier.execute = fake_l6  # type: ignore[method-assign]

        router = Router(
            cache=cache,
            semantic_cache=_semantic_cache(tmp_path),
            ollama=ollama,
            metrics=metrics,
            frontier=frontier,
            frontier_enabled=True,
            confidence_threshold=0.7,
        )

        result = await router.route(_request())
        assert l6_called is True
        assert result.daari_meta.tier == "L6"
        assert result.daari_meta.escalated_from == "L3"
        assert metrics.tiers["L6"].count == 1

    @pytest.mark.asyncio
    async def test_keeps_l3_when_confidence_passes(self, tmp_path):
        cache = ExactCache(str(tmp_path / "c"), enabled=True)
        metrics = Metrics()
        l6_called = False

        async def fake_l3(request: InternalRequest) -> InternalResponse:
            return _l3_response("This is a solid local answer with enough length.")

        async def fake_l6(*args, **kwargs):
            nonlocal l6_called
            l6_called = True
            raise AssertionError("L6 should not be called")

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_l3  # type: ignore[method-assign]
        frontier = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key="sk-test",
        )
        frontier.execute = fake_l6  # type: ignore[method-assign]

        router = Router(
            cache=cache,
            semantic_cache=_semantic_cache(tmp_path),
            ollama=ollama,
            metrics=metrics,
            frontier=frontier,
            frontier_enabled=True,
            confidence_threshold=0.7,
        )

        result = await router.route(_request())
        assert l6_called is False
        assert result.daari_meta.tier == "L3"
        assert result.daari_meta.confidence == 1.0
        assert metrics.tiers["L3"].count == 1

    @pytest.mark.asyncio
    async def test_returns_l3_with_warning_when_frontier_disabled(self, tmp_path):
        cache = ExactCache(str(tmp_path / "c"), enabled=True)
        metrics = Metrics()

        async def fake_l3(request: InternalRequest) -> InternalResponse:
            return _l3_response("short")

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_l3  # type: ignore[method-assign]

        router = Router(
            cache=cache,
            semantic_cache=_semantic_cache(tmp_path),
            ollama=ollama,
            metrics=metrics,
            frontier_enabled=False,
            confidence_threshold=0.7,
        )

        result = await router.route(_request())
        assert result.daari_meta.tier == "L3"
        assert result.daari_meta.confidence == 0.0
        assert result.daari_meta.warning == "below_confidence_threshold"
        assert metrics.tiers["L3"].count == 1

    @pytest.mark.asyncio
    async def test_returns_l3_when_enabled_but_no_api_key(self, tmp_path):
        cache = ExactCache(str(tmp_path / "c"), enabled=True)

        async def fake_l3(request: InternalRequest) -> InternalResponse:
            return _l3_response("nope")

        ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
        ollama.execute = fake_l3  # type: ignore[method-assign]
        frontier = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o-mini",
            api_key=None,
        )

        router = Router(
            cache=cache,
            semantic_cache=_semantic_cache(tmp_path),
            ollama=ollama,
            metrics=Metrics(),
            frontier=frontier,
            frontier_enabled=True,
            confidence_threshold=0.7,
        )

        result = await router.route(_request())
        assert result.daari_meta.tier == "L3"
        assert result.daari_meta.warning == "below_confidence_threshold"

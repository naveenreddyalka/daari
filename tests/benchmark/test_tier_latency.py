"""Optional latency benchmarks — L0 should beat mocked slow L3."""

from __future__ import annotations

import asyncio

import pytest

from daari.cache.exact import ExactCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router


@pytest.mark.benchmark
@pytest.mark.asyncio
async def test_l0_faster_than_l3_mock(tmp_path):
    cache = ExactCache(str(tmp_path / "c"), enabled=True)
    metrics = Metrics()

    async def slow_execute(request: InternalRequest) -> InternalResponse:
        await asyncio.sleep(0.05)
        return InternalResponse(
            content="slow",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=50,
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = slow_execute  # type: ignore[method-assign]
    router = Router(cache=cache, ollama=ollama, metrics=metrics)
    request = InternalRequest(
        messages=[Message(role="user", content="bench")],
        model="llama3.2:3b",
    )

    l3 = await router.route(request)
    l0 = await router.route(request)

    assert l3.daari_meta.tier == "L3"
    assert l0.daari_meta.tier == "L0"
    assert l0.daari_meta.latency_ms < l3.daari_meta.latency_ms

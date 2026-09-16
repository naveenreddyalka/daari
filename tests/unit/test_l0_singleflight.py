"""L0 exact-cache singleflight: coalesce concurrent cold misses (#499)."""

from __future__ import annotations

import asyncio

import pytest

from daari.cache.exact import ExactCache, cache_key
from daari.cache.semantic import SemanticCache
from daari.cache.singleflight import SingleFlight
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


@pytest.mark.asyncio
async def test_singleflight_coalesces_concurrent_fills():
    flight = SingleFlight()
    calls = 0
    started = asyncio.Event()
    release = asyncio.Event()

    async def fill() -> str:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "body"

    leader = asyncio.create_task(flight.do("k", fill))
    await started.wait()
    waiters = [
        asyncio.create_task(flight.do("k", fill)),
        asyncio.create_task(flight.do("k", fill)),
    ]
    await asyncio.sleep(0.01)
    release.set()
    results = await asyncio.gather(leader, *waiters)
    assert results == ["body", "body", "body"]
    assert calls == 1


@pytest.mark.asyncio
async def test_singleflight_error_does_not_poison_retry():
    flight = SingleFlight()
    calls = 0

    async def boom() -> str:
        nonlocal calls
        calls += 1
        raise RuntimeError("upstream down")

    async def ok() -> str:
        nonlocal calls
        calls += 1
        return "recovered"

    with pytest.raises(RuntimeError, match="upstream down"):
        await flight.do("k", boom)
    assert await flight.do("k", ok) == "recovered"
    assert calls == 2


@pytest.mark.asyncio
async def test_router_concurrent_cold_misses_share_one_upstream(tmp_path):
    cache = ExactCache(str(tmp_path / "c"), enabled=True)
    metrics = Metrics()
    calls = 0
    release = asyncio.Event()
    entered = asyncio.Event()

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return InternalResponse(
            content="shared-body",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=10,
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]

    router = Router(
        cache=cache,
        semantic_cache=SemanticCache(
            str(tmp_path / "l1"),
            NoopEmbedder(),
            enabled=False,
        ),
        ollama=ollama,
        metrics=metrics,
    )
    request = InternalRequest(
        messages=[Message(role="user", content="stampede me")],
        model="llama3.2:3b",
    )
    assert cache.get(request) is None
    key = cache_key(request)

    async def one() -> InternalResponse:
        return await router.route(request)

    t1 = asyncio.create_task(one())
    t2 = asyncio.create_task(one())
    t3 = asyncio.create_task(one())
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    # Let waiters park on the in-flight future before releasing upstream.
    await asyncio.sleep(0.05)
    release.set()
    results = await asyncio.gather(t1, t2, t3)

    assert calls == 1
    assert {r.content for r in results} == {"shared-body"}
    assert cache.get(request) is not None
    assert cache.get(request).content == "shared-body"
    # Key still valid for a subsequent L0 hit without another upstream call.
    fourth = await router.route(request)
    assert fourth.daari_meta.tier == "L0"
    assert calls == 1
    assert key == cache_key(request)

"""L1 semantic-cache singleflight: coalesce concurrent same-key lookups/fills (#517)."""

from __future__ import annotations

import asyncio

import pytest

from daari.cache.exact import ExactCache, cache_key
from daari.cache.normalize import normalize_for_embedding
from daari.cache.semantic import SemanticCache, extract_embed_text, l1_flight_key
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router


class BarrierEmbedder:
    """Blocks inside embed until `release` so concurrent nearest calls overlap."""

    def __init__(self, vector: list[float] | None = None) -> None:
        self.vector = vector or [1.0, 0.0, 0.0]
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def embed(self, text: str, *, model: str | None = None) -> list[float] | None:
        self.calls += 1
        self.entered.set()
        await self.release.wait()
        return list(self.vector)


@pytest.mark.asyncio
async def test_nearest_coalesces_concurrent_identical_embeds(tmp_path):
    embedder = BarrierEmbedder()
    cache = SemanticCache(str(tmp_path / "l1"), embedder, enabled=True, similarity_threshold=0.99)
    request = InternalRequest(
        messages=[Message(role="user", content="same embed key")],
        model="llama3.2:3b",
    )
    # Seed so nearest finds something after the shared embed.
    seed = InternalResponse(
        content="cached",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
    )
    embedder.release.set()
    await cache.put(request, seed)
    embedder.calls = 0
    embedder.entered.clear()
    embedder.release.clear()

    async def one() -> tuple[InternalResponse | None, float]:
        return await cache.nearest(request)

    t1 = asyncio.create_task(one())
    await asyncio.wait_for(embedder.entered.wait(), timeout=2.0)
    t2 = asyncio.create_task(one())
    t3 = asyncio.create_task(one())
    await asyncio.sleep(0.05)
    assert embedder.calls == 1
    embedder.release.set()
    results = await asyncio.gather(t1, t2, t3)
    assert embedder.calls == 1
    assert all(r[0] is not None and r[0].content == "cached" for r in results)


@pytest.mark.asyncio
async def test_router_near_identical_ask_misses_share_one_upstream(tmp_path):
    """Same normalized embed key, different L0 keys → one fill (#517)."""
    embedder = BarrierEmbedder()
    # Instant embeds for put/seed paths after the barrier test phase.
    embedder.release.set()

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
            content="A confident l1-shared body with plenty of length to avoid escalation.",
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

    semantic = SemanticCache(
        str(tmp_path / "l1"),
        embedder,
        enabled=True,
        similarity_threshold=0.99,
    )
    router = Router(
        cache=cache,
        semantic_cache=semantic,
        ollama=ollama,
        metrics=metrics,
        frontier_enabled=False,
    )

    a = InternalRequest(
        messages=[Message(role="user", content="hello   world")],
        model="llama3.2:3b",
    )
    b = InternalRequest(
        messages=[Message(role="user", content="hello world")],
        model="llama3.2:3b",
    )
    assert cache_key(a) != cache_key(b)
    assert l1_flight_key(a, text=semantic._embed_text(a)) == l1_flight_key(
        b, text=semantic._embed_text(b)
    )
    assert normalize_for_embedding(extract_embed_text(a)) == normalize_for_embedding(
        extract_embed_text(b)
    )

    t1 = asyncio.create_task(router.route(a))
    t2 = asyncio.create_task(router.route(b))
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    await asyncio.sleep(0.05)
    release.set()
    results = await asyncio.gather(t1, t2)

    assert calls == 1
    assert {r.content for r in results} == {
        "A confident l1-shared body with plenty of length to avoid escalation."
    }


@pytest.mark.asyncio
async def test_agent_turn_skips_l1_fill_coalesce_unchanged(tmp_path):
    """Agent turns keep L0-only coalescing; Ask L1 path stays skipped."""
    from tests.conftest import NoopEmbedder

    semantic = SemanticCache(
        str(tmp_path / "l1"),
        NoopEmbedder(),
        enabled=True,
    )
    cache = ExactCache(str(tmp_path / "c"), enabled=True)
    calls = 0
    release = asyncio.Event()
    entered = asyncio.Event()

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return InternalResponse(
            content="A confident agent answer with plenty of length to avoid escalation.",
            model="llama3.2:3b",
            tool_calls=[{"id": "1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", latency_ms=1
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=cache,
        semantic_cache=semantic,
        ollama=ollama,
        metrics=Metrics(),
        frontier_enabled=False,
    )
    request = InternalRequest(
        messages=[Message(role="user", content="use the tool")],
        model="llama3.2:3b",
        tools=[{"type": "function", "function": {"name": "f", "parameters": {}}}],
    )

    t1 = asyncio.create_task(router.route(request))
    t2 = asyncio.create_task(router.route(request))
    await asyncio.wait_for(entered.wait(), timeout=2.0)
    await asyncio.sleep(0.05)
    release.set()
    results = await asyncio.gather(t1, t2)
    # Identical agent cold misses still share one upstream via L0 singleflight.
    assert calls == 1
    assert all(
        r.content.startswith("A confident agent answer") for r in results
    )

"""Router L1 semantic cache integration (mocked embeddings)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router


class MockEmbedder:
    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {}

    def set_vector(self, text: str, vector: list[float]) -> None:
        self.vectors[text] = vector

    async def embed(self, text: str) -> list[float] | None:
        return self.vectors.get(text)


@pytest.mark.asyncio
async def test_router_l1_hit_on_paraphrase(tmp_path):
    embedder = MockEmbedder()
    original_text = "user:Write a commit message for this diff"
    paraphrase_text = "user:Please draft a commit message for the diff"
    embedder.set_vector(original_text, [1.0, 0.0, 0.0])
    embedder.set_vector(paraphrase_text, [0.99, 0.01, 0.0])

    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    semantic = SemanticCache(
        str(tmp_path / "l1"),
        embedder,
        enabled=True,
        similarity_threshold=0.92,
    )
    metrics = Metrics()
    call_count = 0

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal call_count
        call_count += 1
        return InternalResponse(
            content="feat: add cache layer",
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

    router = Router(cache=cache, semantic_cache=semantic, ollama=ollama, metrics=metrics)

    original = InternalRequest(
        messages=[Message(role="user", content="Write a commit message for this diff")],
        model="llama3.2:3b",
    )
    paraphrase = InternalRequest(
        messages=[Message(role="user", content="Please draft a commit message for the diff")],
        model="llama3.2:3b",
    )

    first = await router.route(original)
    second = await router.route(paraphrase)

    assert first.daari_meta.tier == "L3"
    assert second.daari_meta.tier == "L1"
    assert second.daari_meta.cache_hit is True
    assert second.content == "feat: add cache layer"
    assert call_count == 1
    assert metrics.tiers["L1"].count == 1
    assert metrics.tiers["L1"].cache_hits == 1


@pytest.mark.asyncio
async def test_router_skips_l1_with_tool_calls(tmp_path, semantic_cache_disabled):
    embedder = MockEmbedder()
    embedder.set_vector("user:run tool", [1.0, 0.0])
    semantic = SemanticCache(
        str(tmp_path / "l1"),
        embedder,
        enabled=True,
        similarity_threshold=0.5,
    )
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    metrics = Metrics()
    call_count = 0

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal call_count
        call_count += 1
        return InternalResponse(
            content=f"resp-{call_count}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    router = Router(cache=cache, semantic_cache=semantic, ollama=ollama, metrics=metrics)

    request = InternalRequest(
        messages=[
            Message(
                role="assistant",
                content=None,
                tool_calls=[{"id": "1", "type": "function", "function": {"name": "x"}}],
            ),
            Message(role="user", content="run tool"),
        ],
        model="llama3.2:3b",
    )

    first = await router.route(request)
    second = await router.route(request)

    assert first.daari_meta.tier == "L3"
    assert second.daari_meta.tier == "L3"
    assert call_count == 2
    assert "L1" not in metrics.tiers

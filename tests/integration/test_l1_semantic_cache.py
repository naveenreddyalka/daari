"""Router L1 semantic cache integration (mocked embeddings)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.normalize import normalize_for_embedding
from daari.cache.semantic import SemanticCache, extract_embed_text
from daari.gateway.internal import (
    ContentAudio,
    ContentImage,
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
)
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router


class MockEmbedder:
    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {}

    def set_vector(self, text: str, vector: list[float]) -> None:
        self.vectors[text] = vector

    async def embed(self, text: str) -> list[float] | None:
        return self.vectors.get(text)


class OrthogonalEmbedder:
    """Distinct embed texts get orthogonal unit vectors (cosine ~0)."""

    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {}
        self._next = 0

    async def embed(self, text: str) -> list[float] | None:
        if text not in self.vectors:
            vector = [0.0] * 16
            vector[self._next % 16] = 1.0
            self._next += 1
            self.vectors[text] = vector
        return list(self.vectors[text])


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
    """G1: tool history hits exact L0 on repeat and never L1."""
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
    after_first = call_count
    second = await router.route(request)

    assert first.daari_meta.cache_hit is False
    assert second.daari_meta.tier == "L0"
    assert call_count == after_first
    assert "L1" not in metrics.tiers


def _voice_request(caption: str, clip_data: str) -> InternalRequest:
    return InternalRequest(
        messages=[
            Message(
                role="user",
                content=caption,
                audio=[ContentAudio(data=clip_data, format="wav")],
            )
        ],
        model="llama3.2:3b",
    )


@pytest.mark.asyncio
async def test_l1_misses_when_audio_clip_differs(tmp_path):
    """#1033: same caption + different audio clip must not share an L1 hit."""
    caption = "what did I say?"
    clip_a = _voice_request(caption, "clip-a")
    clip_b = _voice_request(caption, "clip-b")
    assert normalize_for_embedding(extract_embed_text(clip_a)) != normalize_for_embedding(
        extract_embed_text(clip_b)
    )

    embedder = OrthogonalEmbedder()
    # L0 off so the clip-A replay exercises L1, not exact.
    cache = ExactCache(str(tmp_path / "l0"), enabled=False)
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
            content=f"transcript-{call_count}",
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

    seed = InternalResponse(
        content="seeded voice answer",
        model="llama3.2:3b",
        daari_meta=DaariMeta(
            tier="L3",
            executor="ollama",
            provider_id="ollama",
            latency_ms=1,
        ),
    )
    await semantic.put(clip_a, seed)

    miss = await router.route(clip_b)
    assert miss.daari_meta.cache_hit is False
    assert miss.daari_meta.tier != "L1"
    assert "L1" not in metrics.tiers or metrics.tiers["L1"].cache_hits == 0

    hit = await router.route(clip_a)
    assert hit.daari_meta.tier == "L1"
    assert hit.daari_meta.cache_hit is True
    assert hit.content == "seeded voice answer"
    assert metrics.tiers["L1"].cache_hits == 1


def _vision_request(caption: str, image_data: str) -> InternalRequest:
    return InternalRequest(
        messages=[
            Message(
                role="user",
                content=caption,
                images=[ContentImage(data=image_data, media_type="image/png")],
            )
        ],
        model="llama3.2:3b",
    )


@pytest.mark.asyncio
async def test_l1_misses_when_image_differs(tmp_path):
    """#1039: same caption + different image must not share an L1 hit."""
    caption = "what is in this picture?"
    image_a = _vision_request(caption, "img-a")
    image_b = _vision_request(caption, "img-b")
    assert normalize_for_embedding(extract_embed_text(image_a)) != normalize_for_embedding(
        extract_embed_text(image_b)
    )

    embedder = OrthogonalEmbedder()
    cache = ExactCache(str(tmp_path / "l0"), enabled=False)
    semantic = SemanticCache(
        str(tmp_path / "l1"),
        embedder,
        enabled=True,
        similarity_threshold=0.92,
    )
    metrics = Metrics()

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="vision miss answer",
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

    seed = InternalResponse(
        content="seeded vision answer",
        model="llama3.2:3b",
        daari_meta=DaariMeta(
            tier="L3",
            executor="ollama",
            provider_id="ollama",
            latency_ms=1,
        ),
    )
    await semantic.put(image_a, seed)

    miss = await router.route(image_b)
    assert miss.daari_meta.cache_hit is False
    assert miss.daari_meta.tier != "L1"
    assert "L1" not in metrics.tiers or metrics.tiers["L1"].cache_hits == 0

    hit = await router.route(image_a)
    assert hit.daari_meta.tier == "L1"
    assert hit.daari_meta.cache_hit is True
    assert hit.content == "seeded vision answer"
    assert metrics.tiers["L1"].cache_hits == 1

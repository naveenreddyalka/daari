"""Cached-draft injection for L1 near-misses (issue #21)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.frontier import FrontierExecutor
from daari.router.router import OllamaExecutor, Router


class VecEmbedder:
    """Deterministic embedder: keyword-controlled unit vectors."""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    async def embed(self, text: str) -> list[float] | None:
        for key, vec in self.mapping.items():
            if key in text:
                return vec
        return [1.0, 0.0]


# cosine([1,0],[0.8,0.6]) = 0.8 (draft band); cosine([1,0],[0.6,0.8]) = 0.6 (below)
EMBEDS = {
    "seed prompt": [1.0, 0.0],
    "near prompt": [0.8, 0.6],
    "far prompt": [0.6, 0.8],
}


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")


def _semantic(tmp_path) -> SemanticCache:
    return SemanticCache(
        path=str(tmp_path / "l1"),
        embedder=VecEmbedder(EMBEDS),
        enabled=True,
        similarity_threshold=0.88,
    )


def _seed_response() -> InternalResponse:
    return InternalResponse(
        content="The seeded prior answer about caches.",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
    )


@pytest.mark.asyncio
async def test_nearest_returns_below_threshold_entry(tmp_path):
    cache = _semantic(tmp_path)
    await cache.put(_request("seed prompt"), _seed_response())

    response, similarity = await cache.nearest(_request("near prompt"))
    assert response is not None
    assert response.content == "The seeded prior answer about caches."
    assert similarity == pytest.approx(0.8)

    hit, _ = await cache.get(_request("near prompt"))
    assert hit is None, "get must still enforce the similarity threshold"


def _router(tmp_path, *, seen: dict, frontier: FrontierExecutor | None = None, l3_content: str = "A confident local answer with plenty of length.") -> Router:
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen["l3_request"] = request.model_copy(deep=True)
        return InternalResponse(
            content=l3_content,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    executor.execute = fake_execute  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=_semantic(tmp_path),
        ollama=executor,
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=frontier is not None,
        confidence_threshold=0.7,
        l1_draft_threshold=0.75,
    )


def _draft_messages(request: InternalRequest) -> list[Message]:
    return [
        m
        for m in request.messages
        if m.role == "system" and "previous answer to a similar question" in (m.content or "")
    ]


@pytest.mark.asyncio
async def test_draft_injected_for_near_miss(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    response = await router.route(_request("near prompt"))

    drafts = _draft_messages(seen["l3_request"])
    assert len(drafts) == 1
    assert "The seeded prior answer about caches." in drafts[0].content
    assert response.daari_meta.tier == "L3"


@pytest.mark.asyncio
async def test_no_draft_below_band(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    await router.route(_request("far prompt"))

    assert _draft_messages(seen["l3_request"]) == []


@pytest.mark.asyncio
async def test_exact_match_is_l1_hit_not_draft(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    response = await router.route(_request("seed prompt"))

    assert response.daari_meta.tier == "L1"
    assert response.daari_meta.cache_hit is True
    assert "l3_request" not in seen


@pytest.mark.asyncio
async def test_draft_not_persisted_into_l0_key(tmp_path):
    """The draft must only affect generation, never the cache key."""
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    first = await router.route(_request("near prompt"))
    second = await router.route(_request("near prompt"))

    assert first.daari_meta.tier == "L3"
    assert second.daari_meta.tier == "L0", "identical client request should hit L0 afterwards"


@pytest.mark.asyncio
async def test_draft_reaches_frontier_escalation(tmp_path):
    seen: dict = {}
    frontier = FrontierExecutor(
        base_url="https://api.openai.com/v1", default_model="gpt-4o-mini", api_key="sk-test"
    )

    async def fake_l6(request: InternalRequest, *, escalated_from: str, local_confidence: float):
        seen["l6_request"] = request.model_copy(deep=True)
        return InternalResponse(
            content="Frontier answer built on the draft, long enough to be confident.",
            model="gpt-4o-mini",
            daari_meta=DaariMeta(
                tier="L6", executor="frontier", provider_id="openai", latency_ms=50
            ),
        )

    frontier.execute = fake_l6  # type: ignore[method-assign]
    # "no" forces low confidence at every local tier, triggering L6.
    router = _router(tmp_path, seen=seen, frontier=frontier, l3_content="no")
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    response = await router.route(_request("near prompt"))

    assert response.daari_meta.tier == "L6"
    assert len(_draft_messages(seen["l6_request"])) == 1

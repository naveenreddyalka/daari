"""The #168 verifier must run on the live serve paths (#206).

`SemanticCache.get()` applies the lexical verifier, but the router serves L1
from `nearest()` (both non-streaming and streaming), so since the draft-band
refactor the verifier never ran on a real request: "what is 15% of 300" was
served the cached answer for "what is 15% of 200". These tests pin the veto at
the router level, where the bug lived.
"""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.cache.verify import LexicalVerifier
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router

GENERATED = "A freshly generated answer with plenty of length."
STORED_ANSWER = "30 is the answer"


class SameVecEmbedder:
    """Every text embeds identically, so cosine similarity is always 1.0.

    That makes every candidate an above-threshold hit and leaves the verifier
    as the only thing standing between a near-miss and a wrong answer.
    """

    async def embed(self, text: str) -> list[float] | None:
        return [1.0, 0.0, 0.0]


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")


def _seed_response(content: str = STORED_ANSWER) -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
    )


def _router(tmp_path, *, seen: dict, verifier=None, metrics: Metrics | None = None) -> Router:
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        seen["l3_request"] = request.model_copy(deep=True)
        return InternalResponse(
            content=GENERATED,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    async def fake_stream(request: InternalRequest):
        seen["stream_request"] = request.model_copy(deep=True)
        yield {"message": {"content": GENERATED}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    executor.execute = fake_execute  # type: ignore[method-assign]
    executor.stream = fake_stream  # type: ignore[method-assign]
    metrics = metrics or Metrics()
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"),
            embedder=SameVecEmbedder(),
            enabled=True,
            similarity_threshold=0.88,
            verifier=verifier,
            metrics=metrics,
        ),
        ollama=executor,
        metrics=metrics,
        frontier=None,
        frontier_enabled=False,
        l1_draft_threshold=0.75,
    )


async def _collect_stream_content(router: Router, request: InternalRequest) -> str:
    parts: list[str] = []
    async for chunk in router.stream_openai_chunks(request):
        for line in chunk.splitlines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            payload = json.loads(line[len("data: ") :])
            for choice in payload.get("choices", []):
                delta = choice.get("delta", {})
                if delta.get("content"):
                    parts.append(delta["content"])
    return "".join(parts)


def _draft_messages(request: InternalRequest) -> list[Message]:
    return [
        m
        for m in request.messages
        if m.role == "system" and "previous answer to a similar question" in (m.content or "")
    ]


@pytest.mark.asyncio
async def test_route_vetoes_near_miss_above_threshold(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen, verifier=LexicalVerifier())
    await router.semantic_cache.put(_request("what is 15% of 200"), _seed_response())

    response = await router.route(_request("what is 15% of 300"))

    assert response.daari_meta.tier == "L3", "a vetoed hit must generate, not serve"
    assert response.content == GENERATED
    assert STORED_ANSWER not in response.content


@pytest.mark.asyncio
async def test_vetoed_hit_still_seeds_the_draft_band(tmp_path):
    """The veto blocks serving; the entry may still assist generation as a draft."""
    seen: dict = {}
    router = _router(tmp_path, seen=seen, verifier=LexicalVerifier())
    await router.semantic_cache.put(_request("what is 15% of 200"), _seed_response())

    await router.route(_request("what is 15% of 300"))

    drafts = _draft_messages(seen["l3_request"])
    assert len(drafts) == 1
    assert STORED_ANSWER in drafts[0].content


@pytest.mark.asyncio
async def test_route_serves_verified_paraphrase(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen, verifier=LexicalVerifier())
    await router.semantic_cache.put(_request("how do I list files"), _seed_response("use ls"))

    response = await router.route(_request("how can I list files"))

    assert response.daari_meta.tier == "L1"
    assert response.daari_meta.cache_hit is True
    assert response.content == "use ls"


@pytest.mark.asyncio
async def test_route_without_verifier_serves_near_miss(tmp_path):
    """Documents verify=none: the veto above comes from the verifier, not the threshold."""
    seen: dict = {}
    router = _router(tmp_path, seen=seen, verifier=None)
    await router.semantic_cache.put(_request("what is 15% of 200"), _seed_response())

    response = await router.route(_request("what is 15% of 300"))

    assert response.daari_meta.tier == "L1"


@pytest.mark.asyncio
async def test_route_veto_increments_avoided_counter(tmp_path):
    seen: dict = {}
    metrics = Metrics()
    router = _router(tmp_path, seen=seen, verifier=LexicalVerifier(), metrics=metrics)
    await router.semantic_cache.put(_request("what is 15% of 200"), _seed_response())

    await router.route(_request("what is 15% of 300"))

    snapshot = metrics.snapshot(include_histograms=True)
    assert snapshot["cache_false_hits_avoided"] == 1


@pytest.mark.asyncio
async def test_stream_vetoes_near_miss_above_threshold(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen, verifier=LexicalVerifier())
    await router.semantic_cache.put(_request("what is 15% of 200"), _seed_response())

    content = await _collect_stream_content(router, _request("what is 15% of 300"))

    assert content == GENERATED, "streaming must not serve a vetoed near-miss"
    assert "stream_request" in seen, "generation must have run"


@pytest.mark.asyncio
async def test_stream_serves_verified_paraphrase(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen, verifier=LexicalVerifier())
    await router.semantic_cache.put(_request("how do I list files"), _seed_response("use ls"))

    content = await _collect_stream_content(router, _request("how can I list files"))

    assert content == "use ls"
    assert "stream_request" not in seen, "a verified L1 hit must not reach the model"


@pytest.mark.asyncio
async def test_unverifiable_legacy_entry_is_not_served_by_route(tmp_path):
    """Entries without prompt text (pre-#168) cannot be checked, so must not serve."""
    seen: dict = {}
    router = _router(tmp_path, seen=seen, verifier=LexicalVerifier())
    await router.semantic_cache.put(_request("original question"), _seed_response())
    entries = router.semantic_cache._load_entries()
    entries[0].pop("prompt_text", None)
    router.semantic_cache._save_entries(entries)

    response = await router.route(_request("original question"))

    assert response.daari_meta.tier == "L3"
    assert response.content == GENERATED

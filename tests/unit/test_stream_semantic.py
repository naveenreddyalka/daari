"""Streaming path: L1 semantic hits + draft injection parity (issue #43).

The non-stream route serves L1 hits and injects near-miss drafts; before
this issue the streaming path only knew about L0. Cursor traffic is
effectively all streaming, so L1 must work there too.
"""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
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

GENERATED = "A generated streaming answer with plenty of length."


def _request(text: str, *, tools: list | None = None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="llama3.2:3b",
        tools=tools,
    )


def _seed_response() -> InternalResponse:
    return InternalResponse(
        content="The seeded prior answer about caches.",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
    )


def _router(tmp_path, *, seen: dict) -> Router:
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b", tier="L3")

    async def fake_stream(request: InternalRequest):
        seen["stream_request"] = request.model_copy(deep=True)
        seen["stream_calls"] = seen.get("stream_calls", 0) + 1
        yield {"message": {"content": GENERATED}, "done": False}
        yield {"message": {"content": ""}, "done": True}

    executor.stream = fake_stream  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(
            path=str(tmp_path / "l1"),
            embedder=VecEmbedder(EMBEDS),
            enabled=True,
            similarity_threshold=0.88,
        ),
        ollama=executor,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        l1_draft_threshold=0.75,
    )


async def _collect_content(router: Router, request: InternalRequest) -> str:
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
async def test_stream_l1_hit_serves_cached_answer(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    content = await _collect_content(router, _request("seed prompt"))

    assert content == "The seeded prior answer about caches."
    assert "stream_request" not in seen, "L1 hit must not reach the model"
    snapshot = router.metrics.snapshot()
    assert snapshot["L1"]["cache_hits"] == 1


@pytest.mark.asyncio
async def test_stream_draft_band_injects_hint(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    content = await _collect_content(router, _request("near prompt"))

    assert content == GENERATED
    drafts = _draft_messages(seen["stream_request"])
    assert len(drafts) == 1
    assert "The seeded prior answer about caches." in drafts[0].content


@pytest.mark.asyncio
async def test_stream_below_band_no_draft(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    content = await _collect_content(router, _request("far prompt"))

    assert content == GENERATED
    assert _draft_messages(seen["stream_request"]) == []


@pytest.mark.asyncio
async def test_stream_agent_flow_skips_l1(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    tools = [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]
    content = await _collect_content(router, _request("seed prompt", tools=tools))

    assert content == GENERATED, "agent flow must generate, not serve L1"
    assert _draft_messages(seen["stream_request"]) == []


@pytest.mark.asyncio
async def test_stream_writes_back_to_l1(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)

    await _collect_content(router, _request("seed prompt"))

    nearest, similarity = await router.semantic_cache.nearest(_request("seed prompt"))
    assert nearest is not None
    assert similarity == pytest.approx(1.0)
    assert nearest.content == GENERATED


@pytest.mark.asyncio
async def test_stream_l1_hit_respects_no_cache(tmp_path):
    seen: dict = {}
    router = _router(tmp_path, seen=seen)
    await router.semantic_cache.put(_request("seed prompt"), _seed_response())

    request = _request("seed prompt")
    request.meta.no_cache = True
    content = await _collect_content(router, request)

    assert content == GENERATED

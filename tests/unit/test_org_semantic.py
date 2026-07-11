"""Org shared cache: true L1 semantic matching (issue #6)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.enterprise.client import OrgCacheClient, org_l1_key
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


class VecEmbedder:
    """Keyword-controlled deterministic embeddings."""

    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self.mapping = mapping

    async def embed(self, text: str) -> list[float] | None:
        for key, vec in self.mapping.items():
            if key in text:
                return vec
        return [1.0, 0.0]


# cosine([1,0],[0.96,0.28]) ~= 0.96 (above 0.88); cosine([1,0],[0.6,0.8]) = 0.6
EMBEDS = {
    "original prompt": [1.0, 0.0],
    "paraphrased prompt": [0.96, 0.28],
    "unrelated prompt": [0.6, 0.8],
}


def _request(text: str) -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="llama3.2:3b")


def _response(content: str) -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
    )


def _mock_org_server() -> tuple[httpx.MockTransport, dict]:
    """In-memory org cache server speaking the key + similarity protocol."""
    store: dict[str, dict] = {}

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=True))
        na = sum(x * x for x in a) ** 0.5
        nb = sum(y * y for y in b) ** 0.5
        return dot / (na * nb) if na and nb else 0.0

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/org-cache/put":
            body = json.loads(request.content)
            store[f"{body['tier']}:{body['key']}"] = body
            return httpx.Response(200, json={"ok": True})
        if request.url.path == "/v1/org-cache/get":
            key = f"{request.url.params['tier']}:{request.url.params['key']}"
            entry = store.get(key)
            if entry is None:
                return httpx.Response(200, json={"hit": False})
            return httpx.Response(200, json={"hit": True, **entry})
        if request.url.path == "/v1/org-cache/similar":
            body = json.loads(request.content)
            best, best_score = None, 0.0
            for entry in store.values():
                if entry.get("tier") != "L1" or not entry.get("embedding"):
                    continue
                if entry.get("context_key") != body["context_key"]:
                    continue
                score = cosine(body["embedding"], entry["embedding"])
                if score > best_score:
                    best, best_score = entry, score
            if best is None or best_score < body["threshold"]:
                return httpx.Response(200, json={"hit": False})
            return httpx.Response(200, json={"hit": True, "value": best["value"], "similarity": best_score})
        return httpx.Response(404)

    return httpx.MockTransport(handler), store


@pytest.mark.asyncio
async def test_put_l1_uploads_embedding_and_context_key():
    transport, store = _mock_org_server()
    client = OrgCacheClient(
        base_url="http://org.test", transport=transport, embedder=VecEmbedder(EMBEDS)
    )
    request = _request("original prompt")
    await client.put_l1(request, _response("org answer"))

    entry = store[f"L1:{org_l1_key(request)}"]
    assert entry["embedding"] == [1.0, 0.0]
    assert entry["context_key"]


@pytest.mark.asyncio
async def test_get_l1_falls_back_to_similarity_on_key_miss():
    transport, _ = _mock_org_server()
    client = OrgCacheClient(
        base_url="http://org.test",
        transport=transport,
        embedder=VecEmbedder(EMBEDS),
        similarity_threshold=0.88,
    )
    await client.put_l1(_request("original prompt"), _response("org answer"))

    hit = await client.get_l1(_request("paraphrased prompt"))
    assert hit is not None
    assert hit.content == "org answer"

    miss = await client.get_l1(_request("unrelated prompt"))
    assert miss is None


@pytest.mark.asyncio
async def test_get_l1_without_embedder_keeps_key_only_behavior():
    transport, _ = _mock_org_server()
    client = OrgCacheClient(base_url="http://org.test", transport=transport)
    await client.put_l1(_request("original prompt"), _response("org answer"))

    exact = await client.get_l1(_request("original prompt"))
    paraphrase = await client.get_l1(_request("paraphrased prompt"))
    assert exact is not None
    assert paraphrase is None


@pytest.mark.asyncio
async def test_router_l1_org_hit_on_paraphrase(tmp_path):
    transport, _ = _mock_org_server()
    org_cache = OrgCacheClient(
        base_url="http://org.test",
        transport=transport,
        embedder=VecEmbedder(EMBEDS),
        similarity_threshold=0.88,
    )
    await org_cache.put_l1(_request("original prompt"), _response("org answer"))

    async def fail_execute(_request: InternalRequest) -> InternalResponse:
        raise AssertionError("model should not execute on an org L1 hit")

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fail_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=ollama,
        metrics=Metrics(),
        org_cache_client=org_cache,
    )

    response = await router.route(_request("paraphrased prompt"))
    assert response.daari_meta.tier == "L1-org"
    assert response.daari_meta.cache_hit is True
    assert response.content == "org answer"

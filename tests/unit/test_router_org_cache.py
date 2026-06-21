from __future__ import annotations

import asyncio
import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


class FakeOrgCacheClient:
    def __init__(self) -> None:
        self.l0_get_calls = 0
        self.l1_get_calls = 0
        self.l0_put_calls = 0
        self.l1_put_calls = 0
        self.l0_hit: InternalResponse | None = None
        self.l1_hit: InternalResponse | None = None

    async def get_l0(self, _request: InternalRequest) -> InternalResponse | None:
        self.l0_get_calls += 1
        return self.l0_hit

    async def get_l1(self, _request: InternalRequest) -> InternalResponse | None:
        self.l1_get_calls += 1
        return self.l1_hit

    async def put_l0(self, _request: InternalRequest, _response: InternalResponse) -> None:
        self.l0_put_calls += 1

    async def put_l1(self, _request: InternalRequest, _response: InternalResponse) -> None:
        self.l1_put_calls += 1


class FakeOrgLearningClient:
    def __init__(self) -> None:
        self.feedback_payloads: list[object] = []

    async def post_feedback(self, payload: object) -> None:
        self.feedback_payloads.append(payload)


def _request() -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content="hello")], model="llama3.2:3b")


def _response(content: str, tier: str = "L3") -> InternalResponse:
    return InternalResponse(
        content=content,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier=tier, executor="ollama", provider_id="ollama:l3"),
    )


@pytest.mark.asyncio
async def test_router_prefers_local_l0_before_org_l0(tmp_path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    org_cache = FakeOrgCacheClient()
    request = _request()
    cache.put(request, _response("local"))

    async def fail_execute(_request: InternalRequest) -> InternalResponse:
        raise AssertionError("model should not execute")

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fail_execute  # type: ignore[method-assign]
    router = Router(
        cache=cache,
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        metrics=Metrics(),
        ollama=ollama,
        org_cache_client=org_cache,
    )

    result = await router.route(request)
    assert result.daari_meta.tier == "L0"
    assert org_cache.l0_get_calls == 0


@pytest.mark.asyncio
async def test_router_uses_org_l0_on_local_miss(tmp_path):
    cache = ExactCache(str(tmp_path / "l0"), enabled=True)
    org_cache = FakeOrgCacheClient()
    org_cache.l0_hit = _response("org-hit")

    async def fail_execute(_request: InternalRequest) -> InternalResponse:
        raise AssertionError("model should not execute")

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fail_execute  # type: ignore[method-assign]
    router = Router(
        cache=cache,
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        metrics=Metrics(),
        ollama=ollama,
        org_cache_client=org_cache,
    )

    result = await router.route(_request())
    assert result.daari_meta.tier == "L0-org"
    assert org_cache.l0_get_calls == 1


@pytest.mark.asyncio
async def test_router_write_throughs_to_org_cache(tmp_path):
    org_cache = FakeOrgCacheClient()

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return _response("from-model")

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=True),
        metrics=Metrics(),
        ollama=ollama,
        org_cache_client=org_cache,
    )

    result = await router.route(_request())
    assert result.daari_meta.tier == "L3"
    assert org_cache.l0_put_calls == 1
    assert org_cache.l1_put_calls == 1


@pytest.mark.asyncio
async def test_router_posts_org_learning_feedback_non_blocking(tmp_path):
    learning_client = FakeOrgLearningClient()

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return _response("from-model")

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        metrics=Metrics(),
        ollama=ollama,
        org_learning_client=learning_client,  # type: ignore[arg-type]
        org_learning_enabled=True,
    )
    await router.route(_request())
    await asyncio.sleep(0)
    assert len(learning_client.feedback_payloads) == 1

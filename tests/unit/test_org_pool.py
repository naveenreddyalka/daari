"""F4 org inference pool between L5 and L6 (issue #118)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


@pytest.mark.asyncio
async def test_org_pool_before_frontier(tmp_path, monkeypatch):
    cache = ExactCache(path=str(tmp_path / "l0"), enabled=False)
    semantic = SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False)
    local = OllamaExecutor(base_url="http://local", default_model="local", tier="L3")
    pool = OllamaExecutor(base_url="http://pool", default_model="big", tier="L5-org")
    calls: list[str] = []

    async def local_exec(req):
        calls.append("local")
        return InternalResponse(
            content="ok",
            model="local",
            daari_meta=DaariMeta(
                tier="L3", executor="ollama", provider_id="ollama", model="local"
            ),
        )

    async def pool_exec(req):
        calls.append("pool")
        return InternalResponse(
            content="org pool answer that is long enough to score high",
            model="big",
            daari_meta=DaariMeta(
                tier="L5-org", executor="ollama", provider_id="ollama", model="big"
            ),
        )

    monkeypatch.setattr(local, "execute", local_exec)
    monkeypatch.setattr(pool, "execute", pool_exec)
    monkeypatch.setattr(
        "daari.router.router.score_l3_confidence",
        lambda content: 0.95 if "org pool" in content else 0.1,
    )

    router = Router(
        cache=cache,
        semantic_cache=semantic,
        metrics=Metrics(),
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        org_pool=pool,
        frontier_enabled=False,
        confidence_threshold=0.7,
    )
    response = await router.route(
        InternalRequest(messages=[Message(role="user", content="explain quantum")], model="daari")
    )
    assert "pool" in calls
    assert response.daari_meta.tier == "L5-org"

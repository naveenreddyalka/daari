"""Anthropic SSE exact L0 parity with the OpenAI stream path (#600)."""

from __future__ import annotations

import json

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder
from tests.unit.test_router_org_cache import FakeOrgCacheClient


class _Executor(OllamaExecutor):
    def __init__(self, text: str = "anthropic stream answer for cache reuse") -> None:
        super().__init__(base_url="http://test", default_model="llama3.2:3b")
        self.text = text
        self.stream_calls = 0

    async def stream(self, request, **kwargs):  # type: ignore[override]
        self.stream_calls += 1
        yield {"message": {"content": self.text}}
        yield {"done": True}


def _request(text: str = "what is an exact cache?", *, tools: list | None = None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content=text)],
        model="daari",
        tools=tools,
    )


def _router(tmp_path, executor, **kwargs) -> Router:
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=True),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=executor,
        ollama_l3=executor,
        ollama_l4=executor,
        ollama_l5=executor,
        metrics=Metrics(),
        **kwargs,
    )


async def _collect(agen) -> str:
    return "".join([chunk async for chunk in agen])


def _anthropic_meta_tiers(body: str) -> list[str | None]:
    tiers: list[str | None] = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        meta = payload.get("daari_meta") or {}
        if "tier" in meta:
            tiers.append(meta.get("tier"))
    return tiers


def _anthropic_text(body: str) -> str:
    out = []
    for line in body.splitlines():
        if not line.startswith("data: "):
            continue
        payload = json.loads(line[len("data: ") :])
        if payload.get("type") == "content_block_delta":
            out.append(payload.get("delta", {}).get("text") or "")
    return "".join(out)


@pytest.mark.asyncio
async def test_anthropic_stream_identical_request_hits_l0(tmp_path):
    executor = _Executor()
    router = _router(tmp_path, executor)
    request = _request()

    first = await _collect(router.stream_anthropic_events(request))
    second = await _collect(router.stream_anthropic_events(request))

    assert executor.stream_calls == 1, "second Anthropic stream must be L0 without executor"
    assert _anthropic_text(first) == executor.text
    assert _anthropic_text(second) == executor.text
    assert "L0" in _anthropic_meta_tiers(second)
    snap = router.metrics.snapshot()
    assert snap["L0"]["cache_hits"] == 1


@pytest.mark.asyncio
async def test_anthropic_stream_org_l0_on_local_miss(tmp_path):
    executor = _Executor()
    org = FakeOrgCacheClient()
    org.l0_hit = InternalResponse(
        content="org cached anthropic answer",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
    )
    router = _router(tmp_path, executor, org_cache_client=org)

    body = await _collect(router.stream_anthropic_events(_request("org miss local")))

    assert executor.stream_calls == 0
    assert org.l0_get_calls == 1
    assert _anthropic_text(body) == "org cached anthropic answer"
    assert "L0-org" in _anthropic_meta_tiers(body)
    assert router.metrics.snapshot()["L0-org"]["cache_hits"] == 1


@pytest.mark.asyncio
async def test_anthropic_stream_agent_identical_hits_exact_l0(tmp_path):
    """Agent turns keep exact-key L0; no L1 required for stream parity."""
    executor = _Executor(text="tool-aware completion")
    router = _router(tmp_path, executor)
    tools = [{"type": "function", "function": {"name": "run", "parameters": {}}}]
    request = _request("use the run tool carefully", tools=tools)

    await _collect(router.stream_anthropic_events(request))
    second = await _collect(router.stream_anthropic_events(request))

    assert executor.stream_calls == 1
    assert "L0" in _anthropic_meta_tiers(second)

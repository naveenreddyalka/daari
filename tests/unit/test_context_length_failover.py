"""G5: context-too-long on L3 remaps to L4/L5 or compress, traced."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message, RequestMeta
from daari.observability.metrics import Metrics
from daari.observability.trace import TraceStore
from daari.router.failover import is_context_length_error
from daari.router.router import OllamaExecutor, OllamaRequestError, Router
from tests.conftest import NoopEmbedder


def test_detects_ollama_context_length_error():
    err = OllamaRequestError(400, "http://o/api/chat", "prompt exceeds context length")
    assert is_context_length_error(err) is True
    assert is_context_length_error(OllamaRequestError(500, "http://o/api/chat", "busy")) is False
    assert is_context_length_error(RuntimeError("maximum context window exceeded")) is True


@pytest.mark.asyncio
async def test_l3_context_length_escalates_to_l4(tmp_path):
    seen: list[str] = []

    l3 = OllamaExecutor(base_url="http://t", default_model="llama3.2:3b", tier="L3")
    l4 = OllamaExecutor(base_url="http://t", default_model="llama3.1:8b", tier="L4")

    async def l3_exec(_request):
        seen.append("L3")
        raise OllamaRequestError(400, "http://o/api/chat", "context length exceeded")

    async def l4_exec(request):
        seen.append("L4")
        return InternalResponse(
            content="from l4",
            model="llama3.1:8b",
            daari_meta=DaariMeta(tier="L4", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    l3.execute = l3_exec  # type: ignore[method-assign]
    l4.execute = l4_exec  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama_l3=l3,
        ollama_l4=l4,
        metrics=Metrics(),
        frontier_enabled=False,
        confidence_threshold=0.0,
        trace_store=TraceStore(tmp_path / "traces.db"),
    )
    req = InternalRequest(
        messages=[Message(role="user", content="a long prompt")],
        model="daari",
        meta=RequestMeta(tier_override="L3", no_cache=True),
    )
    result = await router.route(req)
    assert seen[0] == "L3"
    assert "L4" in seen
    assert result.content == "from l4"
    assert result.daari_meta.tier == "L4"
    assert result.daari_meta.escalated_from == "L3"
    assert "context_too_long" in (result.daari_meta.warning or "")
    saved = router.trace_store.get(result.daari_meta.trace_id)
    steps = [step["step"] for step in (saved or {}).get("steps") or []]
    assert "context_length_failover" in steps

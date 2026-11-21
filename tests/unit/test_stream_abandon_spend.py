"""Settle ledger spend when the client abandons a frontier stream (#2266)."""

from __future__ import annotations


import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.usage import UsageLedger
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _request(text: str = "explain quantum decoherence carefully") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


class _FiniteFrontier:
    """Many small deltas so the client can aclose mid-relay (after prefetch)."""

    def __init__(self) -> None:
        self.api_key = "sk-test"
        self.default_model = "gpt-4o-mini"
        self.provider = "openai"
        self.last_stream_input_tokens = None
        self.last_stream_output_tokens = None

    async def execute(self, request, escalated_from=None, local_confidence=None):
        raise AssertionError("buffered escalate must not run")

    async def stream(self, request, escalated_from=None, local_confidence=None):
        for i in range(40):
            yield f"token-{i} "


class _LowConfLocal(OllamaExecutor):
    async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
        return InternalResponse(
            content="no",
            model=self.default_model,
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    async def stream(self, request, **kwargs):  # type: ignore[override]
        yield {"message": {"content": "idk"}}
        yield {"done": True}


def _router(tmp_path, frontier, *, ledger: UsageLedger) -> Router:
    local = _LowConfLocal(base_url="http://test", default_model="llama3.2:3b")
    return Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=local,
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.99,
        usage_ledger=ledger,
        frontier_price_per_1k_tokens=0.002,
    )


@pytest.mark.asyncio
async def test_abandoned_frontier_stream_records_estimated_spend(tmp_path, monkeypatch):
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, dict(payload)))

    monkeypatch.setattr("daari.gateway.request_log.log_gateway_event", capture)

    frontier = _FiniteFrontier()
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    router = _router(tmp_path, frontier, ledger=ledger)

    agen = router.stream_openai_chunks(_request())
    seen = 0
    async for chunk in agen:
        if '"content"' in chunk:
            seen += 1
        if seen >= 3:
            break
    await agen.aclose()

    report = ledger.report(days=1)
    assert report["totals"]["frontier_requests"] >= 1
    spend = ledger.frontier_spend_usd(price_per_1k_tokens=0.002)
    assert spend > 0
    assert any(e[0] == "stream_abandon_settled" for e in events)
    abandon = next(e for e in events if e[0] == "stream_abandon_settled")
    assert abandon[1].get("usage_estimated") is True
    assert abandon[1].get("tier") == "L6"
    assert int(abandon[1].get("output_tokens") or 0) > 0


@pytest.mark.asyncio
async def test_completed_frontier_stream_settlement_unchanged(tmp_path):
    class _DoneFrontier(_FiniteFrontier):
        async def stream(self, request, escalated_from=None, local_confidence=None):
            yield "complete answer from frontier path"

    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    router = _router(tmp_path, _DoneFrontier(), ledger=ledger)
    body = "".join([c async for c in router.stream_openai_chunks(_request())])
    assert "complete answer" in body
    assert body.rstrip().endswith("data: [DONE]")
    report = ledger.report(days=1)
    assert report["totals"]["frontier_requests"] >= 1


@pytest.mark.asyncio
async def test_abandoned_local_stream_records_tier_count(tmp_path):
    class _ManyLocal(OllamaExecutor):
        async def stream(self, request, **kwargs):  # type: ignore[override]
            for i in range(40):
                yield {"message": {"content": f"partial-{i} "}}
            yield {"done": True}

    local = _ManyLocal(base_url="http://test", default_model="llama3.2:3b")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=local,
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        metrics=Metrics(),
        frontier=None,
        frontier_enabled=False,
        usage_ledger=ledger,
    )
    agen = router.stream_openai_chunks(_request("say hello please"))
    seen = 0
    async for chunk in agen:
        if "partial-" in chunk:
            seen += 1
        if seen >= 3:
            break
    await agen.aclose()
    report = ledger.report(days=1)
    assert report["totals"]["local_requests"] >= 1
    assert report["totals"]["frontier_requests"] == 0

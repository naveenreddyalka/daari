"""Bill refused/safeguard legs the router falls back from (#2272)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.spend import SpendLedger, install_spend_hook
from daari.observability.usage import UsageLedger
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import FrontierPool, ProviderSlot
from daari.router.refused_leg import is_safeguard_refusal, merge_prior_attempt_cost
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder


def _request(model: str = "daari") -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="do something borderline")],
        model=model,
    )


def _refused_l6(*, cost: float, model: str = "gpt-4o-mini") -> InternalResponse:
    return InternalResponse(
        content="I can't help with that.",
        model=model,
        finish_reason="refusal",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            provider_id="openai",
            model=model,
            input_tokens=100,
            output_tokens=10,
            usage_estimated=False,
            cost_usd=cost,
            daari_cost_usd=0.0,
        ),
    )


def _ok_l6(*, cost: float, model: str = "gpt-4o-mini", provider: str = "openai") -> InternalResponse:
    return InternalResponse(
        content="here is a safe answer",
        model=model,
        finish_reason="stop",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            provider_id=provider,
            model=model,
            input_tokens=80,
            output_tokens=20,
            usage_estimated=False,
            cost_usd=cost,
            daari_cost_usd=0.0,
        ),
    )


def test_is_safeguard_refusal_detects_finish_reasons():
    refused = _refused_l6(cost=0.1)
    assert is_safeguard_refusal(refused) is True
    ok = _ok_l6(cost=0.05)
    assert is_safeguard_refusal(ok) is False
    filtered = InternalResponse(
        content="",
        model="gpt-4o-mini",
        finish_reason="content_filter",
        daari_meta=DaariMeta(tier="L6", executor="frontier"),
    )
    assert is_safeguard_refusal(filtered) is True


def test_merge_prior_attempt_cost_sums_into_serving_meta():
    serving = _ok_l6(cost=0.036)
    merge_prior_attempt_cost(serving, 0.147)
    assert serving.daari_meta.cost_usd == pytest.approx(0.183)


@pytest.mark.asyncio
async def test_frontier_pool_refusal_failover_sums_both_leg_costs():
    primary = FrontierExecutor(
        base_url="http://primary", default_model="a", api_key="k1", provider="primary"
    )
    secondary = FrontierExecutor(
        base_url="http://secondary", default_model="b", api_key="k2", provider="secondary"
    )

    async def refuse(request, *, escalated_from, local_confidence):
        return _refused_l6(cost=0.147, model="a")

    async def ok(request, *, escalated_from, local_confidence):
        return _ok_l6(cost=0.036, model="b", provider="secondary")

    primary.execute = refuse  # type: ignore[method-assign]
    secondary.execute = ok  # type: ignore[method-assign]

    pool = FrontierPool(
        slots=[
            ProviderSlot(id="primary", executor=primary, keys=["k1"]),
            ProviderSlot(id="secondary", executor=secondary, keys=["k2"]),
        ]
    )
    result = await pool.execute(_request(), escalated_from="L3", local_confidence=0.2)
    assert result.content == "here is a safe answer"
    assert result.daari_meta.provider_id == "secondary"
    assert result.daari_meta.cost_usd == pytest.approx(0.183)


@pytest.mark.asyncio
async def test_frontier_pool_single_success_cost_unchanged():
    executor = FrontierExecutor(
        base_url="http://p", default_model="m", api_key="k", provider="openai"
    )

    async def ok(request, *, escalated_from, local_confidence):
        return _ok_l6(cost=0.05)

    executor.execute = ok  # type: ignore[method-assign]
    pool = FrontierPool.from_single(executor)
    result = await pool.execute(_request(), escalated_from="L3", local_confidence=0.1)
    assert result.daari_meta.cost_usd == pytest.approx(0.05)


def _router(tmp_path, frontier, *, ledger: UsageLedger, virtual_models=None) -> Router:
    local = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=local,
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        usage_ledger=ledger,
        frontier_price_per_1k_tokens=0.002,
        virtual_models=virtual_models or {},
    )
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    router.spend_ledger = spend
    install_spend_hook(ledger, spend)
    return router


@pytest.mark.asyncio
async def test_virtual_model_refused_l6_then_peer_bills_both(tmp_path):
    class _TwoShotFrontier:
        api_key = "sk-test"
        default_model = "gpt-4o-mini"
        provider = "openai"
        calls = 0

        async def execute(self, request, escalated_from=None, local_confidence=None):
            self.calls += 1
            if self.calls == 1:
                return _refused_l6(cost=0.12, model=request.model or "gpt-4o-mini")
            return _ok_l6(cost=0.04, model=request.model or "gpt-4o-mini")

        async def stream(self, request, escalated_from=None, local_confidence=None):
            raise AssertionError("non-stream path")

    frontier = _TwoShotFrontier()
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    router = _router(
        tmp_path,
        frontier,
        ledger=ledger,
        virtual_models={"safe-chat": ["openai/gpt-4o-mini", "openai/gpt-4o"]},
    )
    response = await router.route(_request("safe-chat"))
    assert response.finish_reason == "stop"
    assert response.daari_meta.cost_usd == pytest.approx(0.16)
    spend_rows = list(router.spend_ledger.iter_rows(since="1970-01-01T00:00:00+00:00"))
    assert spend_rows
    assert float(spend_rows[0]["cost_usd"]) == pytest.approx(0.16)
    assert frontier.calls == 2


@pytest.mark.asyncio
async def test_local_refusal_failover_stays_zero_cost(tmp_path):
    class _LocalRefuse(OllamaExecutor):
        async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
            return InternalResponse(
                content="nope",
                model=self.default_model,
                finish_reason="refusal",
                daari_meta=DaariMeta(
                    tier="L3",
                    executor="ollama",
                    provider_id="ollama",
                    model=self.default_model,
                    cost_usd=0.0,
                    daari_cost_usd=0.0,
                ),
            )

    class _OkFrontier:
        api_key = "sk-test"
        default_model = "gpt-4o-mini"
        provider = "openai"

        async def execute(self, request, escalated_from=None, local_confidence=None):
            return _ok_l6(cost=0.03)

        async def stream(self, request, escalated_from=None, local_confidence=None):
            raise AssertionError("non-stream path")

    local = _LocalRefuse(base_url="http://test", default_model="llama3.2:3b")
    ledger = UsageLedger(tmp_path / "usage.sqlite3")
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=local,
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        metrics=Metrics(),
        frontier=_OkFrontier(),
        frontier_enabled=True,
        usage_ledger=ledger,
        frontier_price_per_1k_tokens=0.002,
        virtual_models={"safe-chat": ["L3", "L6"]},
    )
    spend = SpendLedger(tmp_path / "spend.sqlite3", enabled=True)
    router.spend_ledger = spend
    install_spend_hook(ledger, spend)
    response = await router.route(_request("safe-chat"))
    assert response.daari_meta.tier == "L6"
    assert response.daari_meta.cost_usd == pytest.approx(0.03)
    spend_rows = list(spend.iter_rows(since="1970-01-01T00:00:00+00:00"))
    assert spend_rows
    assert float(spend_rows[0]["cost_usd"]) == pytest.approx(0.03)

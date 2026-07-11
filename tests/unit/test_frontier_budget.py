"""Frontier daily budget guard (issue #15)."""

from __future__ import annotations

import pytest

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.observability.usage import UsageLedger
from daari.router.frontier import FrontierExecutor
from daari.router.router import OllamaExecutor, Router
from tests.conftest import NoopEmbedder

PRICE = 0.002  # USD per 1k tokens


def _request() -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="explain routing")],
        model="llama3.2:3b",
    )


def _low_confidence_l3(request: InternalRequest) -> InternalResponse:
    return InternalResponse(
        content="no",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
    )


def _build_router(tmp_path, *, ledger: UsageLedger, daily_budget_usd: float, on_l6_called) -> Router:
    async def fake_l3(request: InternalRequest) -> InternalResponse:
        return _low_confidence_l3(request)

    async def fake_l6(
        request: InternalRequest,
        *,
        escalated_from: str,
        local_confidence: float,
    ) -> InternalResponse:
        on_l6_called()
        return InternalResponse(
            content="Frontier answer with enough detail to be confident.",
            model="gpt-4o-mini",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="openai",
                latency_ms=100,
                model="gpt-4o-mini",
                escalated_from=escalated_from,
            ),
        )

    ollama = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    ollama.execute = fake_l3  # type: ignore[method-assign]
    frontier = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="sk-test",
    )
    frontier.execute = fake_l6  # type: ignore[method-assign]
    return Router(
        cache=ExactCache(str(tmp_path / "c"), enabled=False),
        semantic_cache=SemanticCache(path=str(tmp_path / "l1"), embedder=NoopEmbedder(), enabled=False),
        ollama=ollama,
        metrics=Metrics(),
        frontier=frontier,
        frontier_enabled=True,
        confidence_threshold=0.7,
        usage_ledger=ledger,
        frontier_daily_budget_usd=daily_budget_usd,
        frontier_price_per_1k_tokens=PRICE,
    )


def _seed_l6_spend(ledger: UsageLedger, usd: float) -> None:
    # chars = usd / price * 1000 tokens * 4 chars/token
    chars = int(usd / PRICE * 1000 * 4)
    ledger.record(tier="L6", prompt_chars=chars, completion_chars=0)


def test_ledger_frontier_spend_math(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    _seed_l6_spend(ledger, 0.01)
    assert ledger.frontier_spend_usd(price_per_1k_tokens=PRICE) == pytest.approx(0.01)
    # Local tiers do not count as spend.
    ledger.record(tier="L3", prompt_chars=100_000, completion_chars=100_000)
    assert ledger.frontier_spend_usd(price_per_1k_tokens=PRICE) == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_escalation_blocked_when_budget_exceeded(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    _seed_l6_spend(ledger, 0.02)
    l6_calls = 0

    def on_l6():
        nonlocal l6_calls
        l6_calls += 1

    router = _build_router(tmp_path, ledger=ledger, daily_budget_usd=0.01, on_l6_called=on_l6)
    result = await router.route(_request())

    assert l6_calls == 0
    assert result.daari_meta.tier in {"L3", "L4", "L5"}
    assert result.daari_meta.warning == "frontier_budget_exceeded"


@pytest.mark.asyncio
async def test_escalation_blocked_at_exact_budget(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    _seed_l6_spend(ledger, 0.01)
    l6_calls = 0

    def on_l6():
        nonlocal l6_calls
        l6_calls += 1

    router = _build_router(tmp_path, ledger=ledger, daily_budget_usd=0.01, on_l6_called=on_l6)
    result = await router.route(_request())

    assert l6_calls == 0
    assert result.daari_meta.warning == "frontier_budget_exceeded"


@pytest.mark.asyncio
async def test_escalation_allowed_under_budget(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    _seed_l6_spend(ledger, 0.005)
    l6_calls = 0

    def on_l6():
        nonlocal l6_calls
        l6_calls += 1

    router = _build_router(tmp_path, ledger=ledger, daily_budget_usd=0.01, on_l6_called=on_l6)
    result = await router.route(_request())

    assert l6_calls == 1
    assert result.daari_meta.tier == "L6"


@pytest.mark.asyncio
async def test_zero_budget_means_unlimited(tmp_path):
    ledger = UsageLedger(path=tmp_path / "ledger.sqlite3")
    _seed_l6_spend(ledger, 100.0)
    l6_calls = 0

    def on_l6():
        nonlocal l6_calls
        l6_calls += 1

    router = _build_router(tmp_path, ledger=ledger, daily_budget_usd=0.0, on_l6_called=on_l6)
    result = await router.route(_request())

    assert l6_calls == 1
    assert result.daari_meta.tier == "L6"

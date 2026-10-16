"""Anthropic Opus fast mode: forward speed, bill from usage.speed (#1702)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.sampling import SamplingParams
from daari.observability.spend import SpendContext, SpendLedger, compute_request_usd
from daari.pricing import anthropic_speed_factor, cost_usd, resolve_anthropic_speed
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.router import AppContext
from daari.server.app import create_app


def _request(*, model: str, speed: str | None) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model=model,
        sampling=SamplingParams(max_tokens=16, speed=speed),
    )


def test_opus_55_forwards_fast_without_beta():
    decision = resolve_anthropic_speed(
        model="claude-opus-5-5", speed="fast", anthropic_beta=None
    )
    assert decision.speed == "fast"
    assert decision.warning is None
    payload = to_anthropic_payload(
        _request(model="claude-opus-5-5", speed=decision.speed),
        model="claude-opus-5-5",
    )
    assert payload["speed"] == "fast"


def test_opus_5_requires_fast_mode_beta():
    blocked = resolve_anthropic_speed(
        model="claude-opus-5", speed="fast", anthropic_beta=None
    )
    assert blocked.speed is None
    assert blocked.warning == "fast_mode_beta_required"
    allowed = resolve_anthropic_speed(
        model="claude-opus-5-20260601",
        speed="fast",
        anthropic_beta="fast-mode-2026-02-01",
    )
    assert allowed.speed == "fast"
    assert allowed.warning is None


def test_unsupported_model_clears_fast():
    decision = resolve_anthropic_speed(
        model="claude-sonnet-4-5", speed="fast", anthropic_beta=None
    )
    assert decision.speed is None
    assert decision.warning == "fast_unsupported_model"
    payload = to_anthropic_payload(
        _request(model="claude-sonnet-4-5", speed=decision.speed),
        model="claude-sonnet-4-5",
    )
    assert "speed" not in payload


def test_usage_speed_bills_double_only_when_provider_says_fast():
    assert anthropic_speed_factor("fast") == 2.0
    assert anthropic_speed_factor("standard") == 1.0
    standard = cost_usd(
        "claude-opus-5-5",
        1_000_000,
        1_000_000,
        None,
        fallback_per_1k=0.004,
        usage_speed="standard",
    )
    fast = cost_usd(
        "claude-opus-5-5",
        1_000_000,
        1_000_000,
        None,
        fallback_per_1k=0.004,
        usage_speed="fast",
    )
    assert fast == pytest.approx(standard * 2)


def test_spend_row_records_provider_speed_and_fast_cost(tmp_path):
    ledger = SpendLedger(tmp_path / "spend.sqlite3")
    ctx = SpendContext(
        requested_model="claude-opus-5-5",
        pricing=None,
        fallback_per_1k=0.004,
        usage_speed="fast",
    )
    fast_cost, _ = compute_request_usd(
        tier="L6",
        model="claude-opus-5-5",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.004,
        usage_speed="fast",
    )
    standard_cost, _ = compute_request_usd(
        tier="L6",
        model="claude-opus-5-5",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_tokens=0,
        pricing=None,
        fallback_per_1k=0.004,
        usage_speed="standard",
    )
    assert fast_cost == pytest.approx(standard_cost * 2)
    ledger.record(
        request_id="fast-1",
        model="claude-opus-5-5",
        tier="L6",
        input_tokens=1_000_000,
        cost_usd=fast_cost,
        usage_speed=ctx.usage_speed or "",
    )
    rows = list(ledger.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert rows[-1]["usage_speed"] == "fast"
    assert rows[-1]["cost_usd"] == pytest.approx(fast_cost)


@pytest.mark.asyncio
async def test_messages_response_passes_usage_speed(settings, monkeypatch):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model=request.model,
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="anthropic",
                model=request.model,
                input_tokens=12,
                output_tokens=4,
                usage_speed="fast",
            ),
        )

    monkeypatch.setattr(app.state.ctx.router, "route", fake_route)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-opus-5-5",
                "max_tokens": 16,
                "speed": "fast",
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["usage"]["speed"] == "fast"
    assert body["usage"]["input_tokens"] == 12


def test_stream_usage_includes_provider_speed(tmp_path, settings):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.observability.metrics import Metrics
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    executor = OllamaExecutor(base_url="http://test", default_model="llama")
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        metrics=Metrics(),
        ollama=executor,
        ollama_l3=executor,
        pricing=settings.pricing,
        frontier_price_per_1k_tokens=0.002,
    )
    served = InternalResponse(
        content="ok",
        model="claude-opus-5-5",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            model="claude-opus-5-5",
            input_tokens=10,
            output_tokens=2,
            usage_speed="standard",
        ),
    )
    usage = router._anthropic_stream_usage(
        "L6",
        prompt_tokens=10,
        output_tokens=2,
        served=served,
    )
    assert usage["speed"] == "standard"

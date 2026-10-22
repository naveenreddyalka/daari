"""OpenAI prompt-cache write rates by TTL (30m 1.25× / 12h 2.5×) (#1843 / #1865)."""

from __future__ import annotations

import json

import pytest

from daari.config.settings import ModelPrice, PricingSettings
from daari.gateway.cost_headers import stream_usage_cost
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.pricing import cost_usd, resolve_price
from daari.router.anthropic_messages import request_cache_ttl


def test_default_gpt56_models_have_30m_and_12h_write_rates():
    pricing = PricingSettings()
    for model in ("gpt-5.6", "gpt-5.6-sol", "gpt-6-astra", "gpt-6.1-sol"):
        price = resolve_price(model, pricing, fallback_per_1k=0.002)
        assert price.cache_write_30m_per_1m == pytest.approx(price.input_per_1m * 1.25)
        assert price.cache_write_12h_per_1m == pytest.approx(price.input_per_1m * 2.5)


def test_twelve_hour_write_costs_double_thirty_minute():
    """Identical usage: ttl 12h write component is 2× the 30m write component."""
    pricing = PricingSettings(
        models={
            "gpt-5.6": ModelPrice(
                input_per_1m=4.0,
                output_per_1m=20.0,
                cached_input_per_1m=0.40,
                cache_write_30m_per_1m=5.0,
                cache_write_12h_per_1m=10.0,
            )
        }
    )
    writes = 1_000_000
    thirty = cost_usd(
        "gpt-5.6",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl="30m",
    )
    twelve = cost_usd(
        "gpt-5.6",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl="12h",
    )
    assert thirty == pytest.approx(5.0)
    assert twelve == pytest.approx(10.0)
    assert twelve == pytest.approx(thirty * 2.0)


def test_request_cache_ttl_from_prompt_cache_options():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(prompt_cache_options={"ttl": "12h"}),
    )
    assert request_cache_ttl(req) == "12h"


def test_request_cache_ttl_defaults_30m_when_options_present_without_ttl():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(prompt_cache_options={}),
    )
    assert request_cache_ttl(req) == "30m"


def test_request_cache_ttl_prefers_longest_breakpoint():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(
            prompt_cache_options={
                "ttl": "30m",
                "breakpoints": [
                    {"type": "prompt_cache_breakpoint", "ttl": "30m"},
                    {"type": "prompt_cache_breakpoint", "ttl": "12h"},
                ],
            }
        ),
    )
    assert request_cache_ttl(req) == "12h"


def test_chargeback_docs_note_openai_ttl_write_rates():
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[2]
        / "docs/developer/guides/observability/chargeback.md"
    ).read_text(encoding="utf-8")
    assert "30m" in text and "12h" in text
    assert "1.25" in text or "1.25×" in text or "1.25x" in text
    assert "2.5" in text
    assert "prompt_cache_options" in text


def _gpt56_pricing() -> PricingSettings:
    return PricingSettings(
        models={
            "gpt-5.6": ModelPrice(
                input_per_1m=4.0,
                output_per_1m=20.0,
                cached_input_per_1m=0.40,
                cache_write_30m_per_1m=5.0,
                cache_write_12h_per_1m=10.0,
            )
        }
    )


@pytest.mark.parametrize("ttl,write_rate", [("30m", 5.0), ("12h", 10.0)])
def test_stream_usage_cost_matches_nonstream_cache_write_ttl(ttl: str, write_rate: float):
    """Streamed L6 cost must apply the same TTL write multiplier as non-stream (#1865)."""
    pricing = _gpt56_pricing()
    writes = 1_000_000
    expected = cost_usd(
        "gpt-5.6",
        0,
        0,
        pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl=ttl,
    )
    streamed = stream_usage_cost(
        tier="L6",
        model="gpt-5.6",
        prompt_tokens=0,
        completion_tokens=0,
        pricing=pricing,
        fallback_per_1k=0.002,
        cache_write_tokens=writes,
        cache_ttl=ttl,
    )
    assert expected == pytest.approx(write_rate)
    assert streamed == pytest.approx(expected)


def test_stream_usage_cost_omitted_cache_write_unchanged():
    pricing = _gpt56_pricing()
    assert (
        stream_usage_cost(
            tier="L6",
            model="gpt-5.6",
            prompt_tokens=1_000,
            completion_tokens=10,
            pricing=pricing,
            fallback_per_1k=0.002,
            cache_ttl="12h",
        )
        == cost_usd(
            "gpt-5.6",
            1_000,
            10,
            pricing,
            fallback_per_1k=0.002,
            cache_ttl="12h",
        )
    )


def _openai_sse_with_cache_write(*, write_tokens: int) -> bytes:
    events = [
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {"role": "assistant", "content": "hello"}}],
        },
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        {
            "id": "chatcmpl-1",
            "object": "chat.completion.chunk",
            "choices": [],
            "usage": {
                "prompt_tokens": 1_000,
                "completion_tokens": 4,
                "total_tokens": 1_004,
                "cache_write_tokens": write_tokens,
                "prompt_tokens_details": {"cached_tokens": 0},
            },
        },
    ]
    return "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode() + b"data: [DONE]\n\n"


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl,write_rate", [("30m", 5.0), ("12h", 10.0)])
async def test_streamed_openai_cache_write_ttl_bills(tmp_path, ttl: str, write_rate: float):
    """End-to-end: provider stream usage.cache_write_tokens + request TTL → spend (#1865)."""
    import httpx

    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.gateway.cost_headers import COST_HEADER, StreamOutcome
    from daari.observability.metrics import Metrics
    from daari.observability.spend import SpendLedger, install_spend_hook
    from daari.observability.usage import UsageLedger
    from daari.router.frontier import FrontierExecutor
    from daari.router.router import OllamaExecutor, Router
    from tests.conftest import NoopEmbedder

    writes = 1_000_000
    body = _openai_sse_with_cache_write(write_tokens=writes)
    pricing = _gpt56_pricing()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    frontier = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-5.6",
        api_key="sk-test",
        provider="openai",
        transport=httpx.MockTransport(handler),
    )

    class _Local(OllamaExecutor):
        def __init__(self) -> None:
            super().__init__(base_url="http://test", default_model="llama3.2:3b")

        async def stream(self, request, **kwargs):  # type: ignore[override]
            yield {"message": {"content": "idk"}}
            yield {"done": True, "prompt_eval_count": 8, "eval_count": 1}

    usage = UsageLedger(tmp_path / "usage.sqlite")
    spend = SpendLedger(tmp_path / "spend.sqlite", enabled=True)
    install_spend_hook(usage, spend)
    local = _Local()
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
        confidence_threshold=0.99,
        frontier_price_per_1k_tokens=0.004,
        usage_ledger=usage,
        pricing=pricing,
    )
    router.spend_ledger = spend
    outcome = StreamOutcome()
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(prompt_cache_options={"ttl": ttl}),
    )
    raw = "".join(
        [chunk async for chunk in router.stream_openai_chunks(request, outcome=outcome)]
    )
    usage_payload = None
    for line in raw.splitlines():
        if not line.startswith("data: ") or line.endswith("[DONE]"):
            continue
        payload = json.loads(line[len("data: ") :])
        if payload.get("usage"):
            usage_payload = payload["usage"]
    assert usage_payload is not None
    expected = cost_usd(
        "gpt-5.6",
        1_000,
        4,
        pricing,
        fallback_per_1k=0.004,
        cache_write_tokens=writes,
        cache_ttl=ttl,
    )
    # Write component alone is write_rate; input+output add a little on top.
    assert expected == pytest.approx(write_rate + 1_000 / 1e6 * 4.0 + 4 / 1e6 * 20.0)
    assert usage_payload["cost"] == pytest.approx(expected)
    assert float(outcome.headers()[COST_HEADER]) == pytest.approx(expected)
    rows = list(spend.iter_rows(since="2000-01-01T00:00:00+00:00"))
    assert rows
    assert rows[-1]["cache_write_tokens"] == writes
    assert rows[-1]["cost_usd"] == pytest.approx(expected)
    assert frontier.last_stream_cache_write_tokens == writes

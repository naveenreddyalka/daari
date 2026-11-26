"""Anthropic top-level auto_caching via cache_control (#2221)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.config.settings import Settings
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.frontier import FrontierExecutor


def test_settings_auto_caching_defaults_off():
    assert Settings().frontier.auto_caching is False


def test_to_anthropic_payload_injects_top_level_when_auto_caching():
    req = InternalRequest(
        messages=[
            Message(role="system", content="Stable system."),
            Message(role="user", content="hi"),
        ],
        model="daari",
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", prompt_cache=True, auto_caching=True
    )
    assert payload["cache_control"] == {"type": "ephemeral"}
    # Block-level prompt_cache marking still applies.
    assert payload["system"][-1]["cache_control"]["type"] == "ephemeral"


def test_to_anthropic_payload_omits_top_level_when_auto_caching_off():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", prompt_cache=False, auto_caching=False
    )
    assert "cache_control" not in payload


def test_client_top_level_cache_control_wins_over_dial():
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(cache_control={"type": "ephemeral", "ttl": "1h"}),
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", prompt_cache=False, auto_caching=True
    )
    assert payload["cache_control"] == {"type": "ephemeral", "ttl": "1h"}


def test_from_openai_and_anthropic_bodies_parse_top_level_cache_control():
    openai = SamplingParams.from_openai_body(
        {"cache_control": {"type": "ephemeral", "ttl": "5m"}}
    )
    assert openai.cache_control == {"type": "ephemeral", "ttl": "5m"}
    anthropic = SamplingParams.from_anthropic_body(
        {"cache_control": {"type": "ephemeral"}}
    )
    assert anthropic.cache_control == {"type": "ephemeral"}
    responses = SamplingParams.from_responses_body(
        {"cache_control": {"type": "ephemeral", "ttl": "1h"}}
    )
    assert responses.cache_control == {"type": "ephemeral", "ttl": "1h"}


@pytest.mark.asyncio
async def test_frontier_executor_auto_caching_reaches_anthropic_body():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200, json={"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
        )

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com/v1",
        default_model="claude-sonnet-5-5",
        api_key="k",
        provider="anthropic",
        prompt_cache=False,
        auto_caching=True,
        transport=httpx.MockTransport(handler),
    )
    await executor.execute(
        InternalRequest(
            messages=[Message(role="user", content="hello")],
            model="daari",
        ),
        escalated_from="L3",
        local_confidence=0.4,
    )
    assert captured["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_openai_executor_does_not_leak_top_level_cache_control():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "hi"}}]}
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="k",
        provider="openai",
        auto_caching=True,
        transport=httpx.MockTransport(handler),
    )
    await executor.execute(
        InternalRequest(
            messages=[
                Message(role="system", content="Stable."),
                Message(role="user", content="hello"),
            ],
            model="daari",
            sampling=SamplingParams(cache_control={"type": "ephemeral"}),
        ),
        escalated_from="L3",
        local_confidence=0.4,
    )
    assert "cache_control" not in captured


# --- Prom/stats counters: applied vs client-preserved (#2322) ---


def _auto_caching_counts(metrics) -> tuple[int, int]:
    snap = metrics.snapshot(include_histograms=True)
    return (
        int(snap.get("auto_caching_applied") or 0),
        int(snap.get("auto_caching_client_preserved") or 0),
    )


def test_to_anthropic_payload_records_applied_when_dial_injects():
    from daari.observability.metrics import Metrics

    metrics = Metrics()
    req = InternalRequest(messages=[Message(role="user", content="hi")], model="daari")
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", auto_caching=True, metrics=metrics
    )
    assert payload["cache_control"] == {"type": "ephemeral"}
    assert _auto_caching_counts(metrics) == (1, 0)


def test_to_anthropic_payload_records_client_preserved_when_client_wins():
    from daari.observability.metrics import Metrics

    metrics = Metrics()
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(cache_control={"type": "ephemeral", "ttl": "1h"}),
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", auto_caching=True, metrics=metrics
    )
    assert payload["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
    assert _auto_caching_counts(metrics) == (0, 1)


def test_to_anthropic_payload_records_client_preserved_with_dial_off():
    """Caller-supplied cache_control is forwarded (and counted) even when the dial is off."""
    from daari.observability.metrics import Metrics

    metrics = Metrics()
    req = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        sampling=SamplingParams(cache_control={"type": "ephemeral"}),
    )
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", auto_caching=False, metrics=metrics
    )
    assert payload["cache_control"] == {"type": "ephemeral"}
    assert _auto_caching_counts(metrics) == (0, 1)


def test_to_anthropic_payload_quiet_when_dial_off_and_no_client_cache_control():
    from daari.observability.metrics import Metrics

    metrics = Metrics()
    req = InternalRequest(messages=[Message(role="user", content="hi")], model="daari")
    payload = to_anthropic_payload(
        req, model="claude-sonnet-5-5", auto_caching=False, metrics=metrics
    )
    assert "cache_control" not in payload
    assert _auto_caching_counts(metrics) == (0, 0)


def test_to_anthropic_payload_tolerates_missing_metrics():
    req = InternalRequest(messages=[Message(role="user", content="hi")], model="daari")
    payload = to_anthropic_payload(req, model="claude-sonnet-5-5", auto_caching=True)
    assert payload["cache_control"] == {"type": "ephemeral"}


def _anthropic_ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}
    )


@pytest.mark.asyncio
async def test_frontier_executor_anthropic_increments_applied_and_preserved():
    from daari.observability.metrics import Metrics
    from daari.observability.prometheus import render_prometheus

    metrics = Metrics()
    executor = FrontierExecutor(
        base_url="https://api.anthropic.com/v1",
        default_model="claude-sonnet-5-5",
        api_key="k",
        provider="anthropic",
        prompt_cache=False,
        auto_caching=True,
        transport=httpx.MockTransport(_anthropic_ok),
    )
    executor.metrics = metrics
    await executor.execute(
        InternalRequest(messages=[Message(role="user", content="hello")], model="daari"),
        escalated_from="L3",
        local_confidence=0.4,
    )
    assert _auto_caching_counts(metrics) == (1, 0)
    await executor.execute(
        InternalRequest(
            messages=[Message(role="user", content="hello")],
            model="daari",
            sampling=SamplingParams(cache_control={"type": "ephemeral", "ttl": "1h"}),
        ),
        escalated_from="L3",
        local_confidence=0.4,
    )
    assert _auto_caching_counts(metrics) == (1, 1)
    text = render_prometheus(metrics)
    assert "daari_auto_caching_applied_total 1" in text
    assert "daari_auto_caching_client_preserved_total 1" in text


@pytest.mark.asyncio
async def test_openai_executor_leaves_auto_caching_counters_at_zero():
    from daari.observability.metrics import Metrics

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    metrics = Metrics()
    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-4o-mini",
        api_key="k",
        provider="openai",
        auto_caching=True,
        transport=httpx.MockTransport(handler),
    )
    executor.metrics = metrics
    for sampling in (SamplingParams(), SamplingParams(cache_control={"type": "ephemeral"})):
        await executor.execute(
            InternalRequest(
                messages=[Message(role="user", content="hello")],
                model="daari",
                sampling=sampling,
            ),
            escalated_from="L3",
            local_confidence=0.4,
        )
    assert _auto_caching_counts(metrics) == (0, 0)


@pytest.mark.asyncio
async def test_stats_json_exposes_auto_caching_counters(settings):
    from httpx import ASGITransport, AsyncClient

    from daari.router.router import AppContext
    from daari.server.app import create_app

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = await client.get("/v1/daari/stats")
        assert before.status_code == 200
        assert before.json()["auto_caching_applied"] == 0
        assert before.json()["auto_caching_client_preserved"] == 0
        app.state.ctx.metrics.record_auto_caching_applied()
        app.state.ctx.metrics.record_auto_caching_applied()
        app.state.ctx.metrics.record_auto_caching_client_preserved()
        after = await client.get("/v1/daari/stats")
    assert after.json()["auto_caching_applied"] == 2
    assert after.json()["auto_caching_client_preserved"] == 1

"""x-daari-response-cost-* response headers (issue #278)."""

from __future__ import annotations

import pytest

from daari.config.settings import Settings
from daari.gateway.cost_headers import (
    COST_AVOIDED_HEADER,
    COST_HEADER,
    CACHE_HEADER,
    TIER_HEADER,
    DeferredHeadersStreamingResponse,
    StreamOutcome,
    response_cost_headers,
)
from daari.gateway.internal import DaariMeta
from daari.pricing import cost_usd


def _settings(price_per_1k: float = 0.002) -> Settings:
    return Settings.model_validate({"usage": {"frontier_price_per_1k_tokens": price_per_1k}})


class TestResponseCostHeaders:
    def test_local_tier_costs_nothing_and_reports_avoided_frontier_spend(self):
        meta = DaariMeta(tier="L3", executor="ollama")
        headers = response_cost_headers(
            meta, _settings(0.002), prompt_chars=4000, completion_chars=4000
        )
        assert headers[TIER_HEADER] == "L3"
        assert headers[CACHE_HEADER] == "miss"
        assert float(headers[COST_HEADER]) == 0.0
        # Same basis as `daari report`: chars/4 tokens at the flat frontier rate.
        assert float(headers[COST_AVOIDED_HEADER]) == pytest.approx(2000 / 1000 * 0.002)

    def test_cache_hit_and_draft_map_to_cache_header(self):
        hit = DaariMeta(tier="L0", executor="cache", cache_hit=True)
        draft = DaariMeta(tier="L3", executor="ollama", draft=True)
        assert response_cost_headers(hit, _settings())[CACHE_HEADER] == "hit"
        assert response_cost_headers(draft, _settings())[CACHE_HEADER] == "draft"

    def test_frontier_uses_provider_reported_cost_and_avoids_nothing(self):
        meta = DaariMeta(tier="L6", executor="frontier", model="gpt-4o-mini", cost_usd=0.0123)
        headers = response_cost_headers(meta, _settings(), prompt_chars=400, completion_chars=400)
        assert headers[TIER_HEADER] == "L6"
        assert float(headers[COST_HEADER]) == pytest.approx(0.0123)
        assert float(headers[COST_AVOIDED_HEADER]) == 0.0

    def test_frontier_without_reported_cost_is_priced_from_tokens(self):
        settings = _settings(0.002)
        meta = DaariMeta(
            tier="L6",
            executor="frontier",
            model="gpt-4o-mini",
            input_tokens=1000,
            output_tokens=500,
            cached_tokens=200,
        )
        headers = response_cost_headers(meta, settings)
        expected = cost_usd(
            "gpt-4o-mini",
            1000,
            500,
            settings.pricing,
            fallback_per_1k=0.002,
            cached_input_tokens=200,
        )
        assert expected > 0
        assert float(headers[COST_HEADER]) == pytest.approx(expected)

    def test_values_are_plain_decimal_strings(self):
        meta = DaariMeta(tier="L3", executor="ollama")
        headers = response_cost_headers(meta, _settings(), prompt_chars=4, completion_chars=0)
        assert headers[COST_HEADER] == "0"
        assert "e" not in headers[COST_AVOIDED_HEADER].lower()


class TestStreamOutcome:
    def test_headers_empty_until_router_commits(self):
        outcome = StreamOutcome()
        assert outcome.headers() == {}
        outcome.note("L0", cache_hit=True)
        assert outcome.headers() == {TIER_HEADER: "L0", CACHE_HEADER: "hit"}

    def test_draft_and_miss(self):
        assert StreamOutcome().note("L3", draft=True).headers()[CACHE_HEADER] == "draft"
        assert StreamOutcome().note("L4").headers()[CACHE_HEADER] == "miss"
        assert StreamOutcome().note(None).headers() == {}


async def _run_asgi(response) -> list[dict]:
    sent: list[dict] = []

    async def receive():
        return {"type": "http.request"}

    async def send(message):
        sent.append(message)

    await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    return sent


@pytest.mark.asyncio
async def test_deferred_headers_are_read_when_first_chunk_is_ready():
    outcome = StreamOutcome()

    async def body():
        outcome.note("L0", cache_hit=True)
        yield "data: one\n\n"
        yield "data: two\n\n"

    response = DeferredHeadersStreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
        late_headers=outcome.headers,
    )
    sent = await _run_asgi(response)
    start = sent[0]
    assert start["type"] == "http.response.start"
    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    assert headers["cache-control"] == "no-cache"
    assert headers[TIER_HEADER] == "L0"
    assert headers[CACHE_HEADER] == "hit"
    bodies = [m["body"] for m in sent[1:]]
    assert bodies == [b"data: one\n\n", b"data: two\n\n", b""]


@pytest.mark.asyncio
async def test_deferred_headers_omitted_when_still_unknown():
    async def body():
        yield "data: only\n\n"

    response = DeferredHeadersStreamingResponse(
        body(), media_type="text/event-stream", late_headers=StreamOutcome().headers
    )
    sent = await _run_asgi(response)
    headers = {k.decode(): v.decode() for k, v in sent[0]["headers"]}
    assert TIER_HEADER not in headers
    assert sent[0]["type"] == "http.response.start"


@pytest.mark.asyncio
async def test_deferred_headers_empty_body_still_starts_response():
    async def body():
        return
        yield  # pragma: no cover

    response = DeferredHeadersStreamingResponse(body(), late_headers=dict)
    sent = await _run_asgi(response)
    assert [m["type"] for m in sent] == ["http.response.start", "http.response.body"]

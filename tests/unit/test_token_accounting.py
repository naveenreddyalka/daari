"""Real token counts and per-model pricing (#156, #157).

Every token count used to be `len(chars) // 4` and every cost used one flat
rate, so the savings report, budgets, and spend gauges were all estimates of an
estimate. Providers report usage; read it.
"""

from __future__ import annotations

import json
import sqlite3

import httpx
import pytest

from daari.config.settings import PricingSettings, Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.usage import UsageLedger
from daari.pricing import cost_usd, resolve_price
from daari.router.frontier import FrontierExecutor
from daari.router.router import OllamaExecutor


def _request(text: str = "hello") -> InternalRequest:
    return InternalRequest(messages=[Message(role="user", content=text)], model="daari")


# --- provider-reported usage ------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_execute_captures_reported_token_counts(monkeypatch):
    """Ollama returns prompt_eval_count/eval_count; they must not be discarded."""
    captured = {
        "message": {"content": "hi there"},
        "prompt_eval_count": 41,
        "eval_count": 7,
    }

    class _Response:
        status_code = 200

        def json(self):
            return captured

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", lambda **kw: _Client())
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    response = await executor.execute(_request())
    assert response.daari_meta.input_tokens == 41
    assert response.daari_meta.output_tokens == 7
    assert response.daari_meta.usage_estimated is False


@pytest.mark.asyncio
async def test_frontier_execute_captures_usage():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "frontier answer"}}],
                "usage": {"prompt_tokens": 120, "completion_tokens": 34},
            },
        )

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(_request(), escalated_from="L3", local_confidence=0.2)
    assert response.daari_meta.input_tokens == 120
    assert response.daari_meta.output_tokens == 34
    assert response.daari_meta.usage_estimated is False


@pytest.mark.asyncio
async def test_missing_usage_falls_back_to_estimate_and_is_flagged():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "no usage here"}}]})

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(_request(), escalated_from="L3", local_confidence=0.2)
    assert response.daari_meta.usage_estimated is True
    assert response.daari_meta.output_tokens is not None, "an estimate is still recorded"


# --- ledger schema and migration -------------------------------------------


def test_ledger_records_tokens_model_and_provider(tmp_path):
    ledger = UsageLedger(tmp_path / "ledger.sqlite3")
    ledger.record(
        tier="L6",
        prompt_chars=400,
        completion_chars=80,
        input_tokens=100,
        output_tokens=20,
        model="gpt-4o",
        provider="openai",
    )
    with sqlite3.connect(ledger.path) as conn:
        row = conn.execute(
            "SELECT model, provider, input_tokens, output_tokens FROM usage WHERE tier = 'L6'"
        ).fetchone()
    assert row == ("gpt-4o", "openai", 100, 20)


def test_ledger_migrates_a_pre_token_database(tmp_path):
    """An existing ledger from before this change must keep working."""
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE usage (
                day TEXT NOT NULL, tier TEXT NOT NULL,
                requests INTEGER NOT NULL DEFAULT 0,
                cache_hits INTEGER NOT NULL DEFAULT 0,
                prompt_chars INTEGER NOT NULL DEFAULT 0,
                completion_chars INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, tier)
            );
            CREATE TABLE client_usage (
                day TEXT NOT NULL, client_id TEXT NOT NULL, tier TEXT NOT NULL,
                requests INTEGER NOT NULL DEFAULT 0,
                cache_hits INTEGER NOT NULL DEFAULT 0,
                prompt_chars INTEGER NOT NULL DEFAULT 0,
                completion_chars INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (day, client_id, tier)
            );
            INSERT INTO usage (day, tier, requests, prompt_chars, completion_chars)
            VALUES ('2026-01-01', 'L3', 5, 1000, 500);
            """
        )
    ledger = UsageLedger(path)
    assert ledger.enabled, "migration must not disable the ledger"
    ledger.record(tier="L3", input_tokens=10, output_tokens=5, model="llama3.2:3b")
    report = ledger.report(days=100000)
    assert report["enabled"] is True
    assert report["totals"]["requests"] >= 6, "pre-existing rows must survive"


# --- per-model pricing ------------------------------------------------------


def test_resolve_price_prefers_exact_model_entry():
    pricing = PricingSettings(
        models={"gpt-4o": {"input_per_1m": 2.5, "output_per_1m": 10.0}}
    )
    price = resolve_price("gpt-4o", pricing, fallback_per_1k=0.002)
    assert price.input_per_1m == 2.5
    assert price.output_per_1m == 10.0


def test_resolve_price_falls_back_for_unknown_model():
    pricing = PricingSettings(models={})
    price = resolve_price("some-new-model", pricing, fallback_per_1k=0.002)
    # 0.002 per 1k tokens == 2.00 per 1M, applied to both directions.
    assert price.input_per_1m == pytest.approx(2.0)
    assert price.output_per_1m == pytest.approx(2.0)
    assert price.is_fallback is True


def test_cost_uses_direction_specific_rates():
    pricing = PricingSettings(
        models={"gpt-4o": {"input_per_1m": 2.5, "output_per_1m": 10.0}}
    )
    # 1M input + 1M output should not be priced at a single blended rate.
    usd = cost_usd("gpt-4o", 1_000_000, 1_000_000, pricing, fallback_per_1k=0.002)
    assert usd == pytest.approx(12.5)


def test_flat_rate_is_still_honoured_when_no_table_configured():
    pricing = PricingSettings(models={})
    usd = cost_usd("anything", 500_000, 500_000, pricing, fallback_per_1k=0.002)
    assert usd == pytest.approx(2.0)


def test_ledger_spend_uses_per_model_pricing(tmp_path):
    ledger = UsageLedger(tmp_path / "ledger.sqlite3")
    pricing = PricingSettings(
        models={
            "cheap-model": {"input_per_1m": 1.0, "output_per_1m": 1.0},
            "pricey-model": {"input_per_1m": 100.0, "output_per_1m": 100.0},
        }
    )
    ledger.record(tier="L6", input_tokens=1_000_000, output_tokens=0, model="cheap-model")
    ledger.record(tier="L6", input_tokens=1_000_000, output_tokens=0, model="pricey-model")
    spend = ledger.frontier_spend_usd(pricing=pricing, fallback_per_1k=0.002)
    assert spend == pytest.approx(101.0), "each model must be priced at its own rate"


def test_doctor_warns_about_unpriced_frontier_model():
    from daari.pricing import pricing_warnings

    settings = Settings()
    settings.frontier.enabled = True
    settings.frontier.model = "brand-new-model"
    settings.pricing.models = {}
    warnings = pricing_warnings(settings)
    assert any("brand-new-model" in warning for warning in warnings)


def test_default_pricing_table_covers_the_default_frontier_model():
    settings = Settings()
    price = resolve_price(
        settings.frontier.model, settings.pricing, fallback_per_1k=0.002
    )
    assert price.is_fallback is False, "the shipped default model should be priced"


# --- API surface ------------------------------------------------------------


def test_openai_usage_reports_measured_tokens():
    from daari.gateway.openai import build_chat_completion_payload

    response = InternalResponse(
        content="an answer",
        model="gpt-4o",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            input_tokens=120,
            output_tokens=34,
            usage_estimated=False,
        ),
    )
    payload = build_chat_completion_payload(response, prompt_chars=4000, include_daari_meta=True)
    assert payload["usage"]["prompt_tokens"] == 120
    assert payload["usage"]["completion_tokens"] == 34
    assert payload["usage"]["total_tokens"] == 154
    assert payload["daari_meta"]["usage_estimated"] is False


def test_openai_usage_flags_estimates():
    from daari.gateway.openai import build_chat_completion_payload

    response = InternalResponse(
        content="x" * 40,
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama"),
    )
    payload = build_chat_completion_payload(response, prompt_chars=400, include_daari_meta=True)
    assert payload["usage"]["prompt_tokens"] == 100
    assert payload["daari_meta"]["usage_estimated"] is True


def test_json_shape_unchanged_for_clients():
    """usage must keep exactly the three OpenAI keys clients parse."""
    from daari.gateway.openai import build_chat_completion_payload

    response = InternalResponse(
        content="hi", model="m", daari_meta=DaariMeta(tier="L3", executor="ollama")
    )
    payload = build_chat_completion_payload(response, prompt_chars=8, include_daari_meta=False)
    assert set(payload["usage"]) == {"prompt_tokens", "completion_tokens", "total_tokens"}
    json.dumps(payload)

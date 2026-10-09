"""OpenAI chat-latest rolling alias pricing + catalog (#1509)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.pricing import matching_model_key, resolve_price
from daari.router.capabilities import known_model_capabilities
from daari.router.router import AppContext
from daari.server.app import create_app

BUDGETS = Path("docs/developer/guides/configuration/budgets-frontier.md")


def test_chat_latest_pricing_is_not_fallback():
    """Rolling Instant alias uses published $5/$30/$0.50 rates (#1509)."""
    settings = Settings()
    price = resolve_price("chat-latest", settings.pricing, fallback_per_1k=0.002)
    assert price.is_fallback is False
    assert price.input_per_1m == pytest.approx(5.0)
    assert price.output_per_1m == pytest.approx(30.0)
    assert price.cached_input_per_1m == pytest.approx(0.50)
    # Vendor / path prefixes still resolve to the rolling row.
    assert matching_model_key("openai/chat-latest", settings.pricing.models) == "chat-latest"
    assert matching_model_key("openai.chat-latest", settings.pricing.models) == "chat-latest"
    assert resolve_price(
        "openai/chat-latest", settings.pricing, fallback_per_1k=0.002
    ).is_fallback is False


def test_chat_latest_capabilities():
    caps = known_model_capabilities("chat-latest")
    assert {"tools", "json", "vision", "long_context"} <= set(caps)
    assert known_model_capabilities("openai.chat-latest") == caps


@pytest.mark.asyncio
async def test_chat_latest_appears_on_openai_models(settings):
    settings.frontier.enabled = True
    settings.frontier.providers = []
    from daari.config.settings import FrontierProviderConfig

    settings.frontier.providers = [
        FrontierProviderConfig(id="openai", model="chat-latest"),
    ]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/models")
    assert response.status_code == 200
    ids = {row["id"] for row in response.json()["data"]}
    assert "chat-latest" in ids
    card = next(row for row in response.json()["data"] if row["id"] == "chat-latest")
    assert {"tools", "json", "vision", "long_context"} <= set(card["capabilities"])


def test_budgets_frontier_docs_mention_chat_latest():
    text = BUDGETS.read_text(encoding="utf-8")
    assert "chat-latest" in text
    assert "rolling" in text.lower() or "Instant" in text

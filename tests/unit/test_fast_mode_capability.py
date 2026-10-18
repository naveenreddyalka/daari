"""Catalog cards advertise Anthropic Opus fast mode (#1740)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.router.capabilities import anthropic_capabilities, openai_model_cards
from daari.router.router import AppContext
from daari.server.app import create_app


def test_anthropic_capabilities_advertise_fast_mode_by_id():
    ga = anthropic_capabilities("claude-opus-5-5")["speed"]["fast"]
    assert ga["supported"] is True
    assert ga["beta_header"] is False
    assert ga["input_per_1m"] == pytest.approx(8.0)
    assert ga["output_per_1m"] == pytest.approx(40.0)

    preview = anthropic_capabilities("claude-opus-5")["speed"]["fast"]
    assert preview["supported"] is True
    assert preview["beta_header"] is True
    assert preview["input_per_1m"] == pytest.approx(10.0)
    assert preview["output_per_1m"] == pytest.approx(50.0)

    alias = anthropic_capabilities("claude-opus-4-8")["speed"]["fast"]
    assert alias["supported"] is True
    assert alias["beta_header"] is True

    dated = anthropic_capabilities("claude-opus-5-5-20261001")["speed"]["fast"]
    assert dated["beta_header"] is False
    assert dated["input_per_1m"] == pytest.approx(8.0)

    assert "speed" not in anthropic_capabilities("claude-haiku-4-5")
    assert "speed" not in anthropic_capabilities("claude-sonnet-5-5")
    assert "speed" not in anthropic_capabilities("daari")


def test_openai_catalog_cards_include_fast_mode_extras():
    settings = Settings.model_validate(
        {
            "frontier": {
                "enabled": True,
                "providers": [
                    {"id": "anthropic", "model": "claude-opus-5-5"},
                    {"id": "anthropic", "model": "claude-opus-5"},
                    {"id": "anthropic", "model": "claude-haiku-4-5"},
                ],
            }
        }
    )
    by_id = {card["id"]: card for card in openai_model_cards(settings)}
    fast = by_id["claude-opus-5-5"]["speed"]["fast"]
    assert fast["supported"] is True
    assert fast["beta_header"] is False
    assert fast["input_per_1m"] == pytest.approx(8.0)
    assert fast["output_per_1m"] == pytest.approx(40.0)
    assert by_id["claude-opus-5"]["speed"]["fast"]["beta_header"] is True
    assert "speed" not in by_id["claude-haiku-4-5"]
    assert "speed" not in by_id["daari"]


@pytest.mark.asyncio
async def test_openai_retrieve_unknown_fast_id_includes_speed():
    settings = Settings.model_validate({"frontier": {"enabled": False}})
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        opus = await client.get("/v1/models/claude-opus-5-5")
        haiku = await client.get("/v1/models/claude-haiku-4-5")
    assert opus.status_code == 200
    body = opus.json()
    assert body["speed"]["fast"]["supported"] is True
    assert body["speed"]["fast"]["beta_header"] is False
    assert body["speed"]["fast"]["input_per_1m"] == pytest.approx(8.0)
    assert "speed" not in haiku.json()

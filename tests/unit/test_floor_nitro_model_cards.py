"""Catalog cards for :floor and :nitro copy the target tier's metadata (#1733)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.capabilities import openai_model_cards
from daari.router.router import AppContext
from daari.server.app import create_app


def _by_id(settings) -> dict[str, dict]:
    return {card["id"]: card for card in openai_model_cards(settings)}


def _metadata(card: dict) -> dict:
    return {key: value for key, value in card.items() if key != "id"}


def test_floor_and_nitro_cards_copy_tier_metadata(settings):
    cards = _by_id(settings)
    l3 = settings.models.l3
    nitro_target = settings.models.l5
    assert "daari:floor" in cards
    assert "daari:nitro" in cards
    assert _metadata(cards["daari:floor"]) == _metadata(cards[l3])
    assert _metadata(cards["daari:nitro"]) == _metadata(cards[nitro_target])
    assert cards["daari:floor"]["id"] == "daari:floor"
    assert cards["daari:nitro"]["id"] == "daari:nitro"
    floor_alias = f"{l3}:floor"
    nitro_alias = f"{nitro_target}:nitro"
    assert _metadata(cards[floor_alias]) == _metadata(cards[l3])
    assert cards[floor_alias]["id"] == floor_alias
    assert _metadata(cards[nitro_alias]) == _metadata(cards[nitro_target])
    assert cards[nitro_alias]["id"] == nitro_alias
    ids = [card["id"] for card in openai_model_cards(settings)]
    assert len(ids) == len(set(ids))


def test_nitro_falls_back_when_larger_tiers_unset(settings):
    settings.models.l5 = ""
    settings.models.l4 = ""
    cards = _by_id(settings)
    assert _metadata(cards["daari:nitro"]) == _metadata(cards[settings.models.l3])


@pytest.mark.asyncio
async def test_retrieve_alias_and_unknown_stub(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    l3 = settings.models.l3
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.get("/v1/models")
        floor = await client.get("/v1/models/daari:floor")
        nitro = await client.get("/v1/models/daari:nitro")
        l3_floor = await client.get(f"/v1/models/{l3}:floor")
        unknown = await client.get("/v1/models/not-a-real-model")
    ids = {card["id"] for card in listed.json()["data"]}
    assert "daari:floor" in ids
    assert "daari:nitro" in ids
    assert floor.status_code == 200
    assert floor.json()["id"] == "daari:floor"
    assert floor.json()["capabilities"] == next(
        card["capabilities"] for card in listed.json()["data"] if card["id"] == l3
    )
    assert "context_length" in floor.json()
    assert nitro.json()["id"] == "daari:nitro"
    assert nitro.json()["server_tools"] == next(
        card["server_tools"]
        for card in listed.json()["data"]
        if card["id"] == settings.models.l5
    )
    assert l3_floor.json()["id"] == f"{l3}:floor"
    assert l3_floor.json()["lifecycle"] == next(
        card["lifecycle"] for card in listed.json()["data"] if card["id"] == l3
    )
    stub = unknown.json()
    assert stub["id"] == "not-a-real-model"
    assert stub["capabilities"] == []
    assert "context_length" not in stub

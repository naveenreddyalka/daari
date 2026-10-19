"""Ollama :cloud ids are marked remote on catalog surfaces (#1776)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from daari.config.settings import Settings
from daari.router.capabilities import anthropic_model_cards, openai_model_cards
from daari.router.router import AppContext
from daari.server.app import create_app


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "models": {"l3": "clef:cloud", "l4": "llama3.2:3b"},
            "systemone": {"enabled": False},
        }
    )


def _client(settings: Settings) -> TestClient:
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return TestClient(app)


def test_openai_and_anthropic_cards_mark_cloud_ids():
    settings = _settings()
    openai = {card["id"]: card for card in openai_model_cards(settings)}
    anthropic = {card["id"]: card for card in anthropic_model_cards(settings)}

    cloud = openai["clef:cloud"]
    local = openai["llama3.2:3b"]
    assert cloud["hosted_on"] == "ollama-cloud"
    assert "hosted_on" not in local
    assert anthropic["clef:cloud"]["hosted_on"] == "ollama-cloud"
    assert "hosted_on" not in anthropic["llama3.2:3b"]


def test_ollama_tags_and_show_mark_cloud_ids():
    client = _client(_settings())
    tags = client.get("/api/tags")
    assert tags.status_code == 200
    by_name = {model["name"]: model for model in tags.json()["models"]}

    cloud = by_name["clef:cloud"]
    local = by_name["llama3.2:3b"]
    assert cloud["details"]["family"] == "ollama-cloud"
    assert "remote" in cloud["capabilities"]
    assert cloud["digest"] == "daari-virtual"
    assert local["details"]["family"] == "daari"
    assert "remote" not in local.get("capabilities", [])

    show = client.post("/api/show", json={"model": "clef:cloud"})
    assert show.status_code == 200
    body = show.json()
    assert body["details"]["family"] == "ollama-cloud"
    assert "remote" in body["capabilities"]

    plain = client.post("/api/show", json={"model": "llama3.2:3b"})
    assert plain.json()["details"]["family"] == "daari"
    assert "remote" not in plain.json()["capabilities"]

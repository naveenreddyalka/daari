"""Ollama /api/show advertises thinking controls (#789)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from daari.config.settings import Settings
from daari.gateway.sampling import ollama_thinking_controls
from daari.router.router import AppContext
from daari.server.app import create_app


def _client(settings: Settings | None = None) -> TestClient:
    settings = settings or Settings()
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return TestClient(app)


def test_thinking_controls_match_ollama_think_levels():
    """Documented set: low/medium/high from _REASONING_EFFORT_TO_THINK (no max)."""
    controls = ollama_thinking_controls()
    assert controls == {"values": ["low", "medium", "high"], "default": "medium"}


def test_show_includes_thinking_object_for_thinking_model():
    response = _client().post("/api/show", json={"model": "qwen3:8b"})
    assert response.status_code == 200
    body = response.json()
    assert "thinking" in body["capabilities"]
    assert body["thinking"] == {"values": ["low", "medium", "high"], "default": "medium"}


def test_show_omits_thinking_object_for_plain_model():
    response = _client().post("/api/show", json={"model": "llama3.2:3b"})
    assert response.status_code == 200
    body = response.json()
    assert "thinking" not in body["capabilities"]
    assert "thinking" not in body


def test_tags_omit_thinking_controls_object():
    """Show-only: tags may list the capability string but never the controls object."""
    response = _client().get("/api/tags")
    assert response.status_code == 200
    for model in response.json()["models"]:
        assert "thinking" not in model

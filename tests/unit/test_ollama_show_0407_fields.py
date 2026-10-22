"""Ollama /api/show parity with 0.40.7 renderer/parser/template_source (#1846)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from daari.config.settings import Settings
from daari.gateway.decisions import BUILTIN_LOCAL_MODELS
from daari.router.router import AppContext
from daari.server.app import create_app


def _client(settings: Settings | None = None) -> TestClient:
    settings = settings or Settings()
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return TestClient(app)


def _assert_0407_show_fields(body: dict) -> None:
    assert "renderer" in body
    assert "parser" in body
    assert "template_source" in body
    assert body["renderer"] == ""
    assert body["parser"] == ""
    assert body["template_source"] == "model"


def test_show_includes_0407_fields_for_virtual_model():
    response = _client().post("/api/show", json={"model": "daari"})
    assert response.status_code == 200
    _assert_0407_show_fields(response.json())


def test_show_includes_0407_fields_for_local_decisions_model():
    name = sorted(BUILTIN_LOCAL_MODELS)[0]
    response = _client().post("/api/show", json={"model": name})
    assert response.status_code == 200
    _assert_0407_show_fields(response.json())


def test_tags_omit_0407_show_only_fields():
    """Show-only 0.40.7 fields must not appear on /api/tags model entries."""
    response = _client().get("/api/tags")
    assert response.status_code == 200
    for model in response.json()["models"]:
        assert "renderer" not in model
        assert "parser" not in model
        assert "template_source" not in model

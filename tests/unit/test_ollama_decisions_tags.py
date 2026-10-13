"""Ollama /api/tags advertises local decisions catalog (#1619)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from daari.config.settings import Settings
from daari.gateway.decisions import BUILTIN_LOCAL_MODELS
from daari.router.router import AppContext
from daari.server.app import create_app


def _client(settings: Settings) -> TestClient:
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return TestClient(app)


def test_tags_list_decision_models_when_systemone_on():
    settings = Settings.model_validate(
        {"decisions": {"local_models": ["my-judge"]}}
    )
    body = _client(settings).get("/api/tags").json()
    by_name = {m["name"]: m for m in body["models"]}
    for model_id in BUILTIN_LOCAL_MODELS:
        assert model_id in by_name
        assert "decision" in by_name[model_id]["capabilities"]
        assert "completion" in by_name[model_id]["capabilities"]
    assert "my-judge" in by_name
    assert "decision" in by_name["my-judge"]["capabilities"]


def test_tags_omit_decision_models_when_systemone_off():
    settings = Settings.model_validate({"systemone": {"enabled": False}})
    names = {m["name"] for m in _client(settings).get("/api/tags").json()["models"]}
    assert "nimble" not in names
    assert "clef" not in names


def test_show_decision_model_includes_decision_capability():
    response = _client(Settings()).post("/api/show", json={"model": "nimble"})
    assert response.status_code == 200
    caps = response.json()["capabilities"]
    assert "decision" in caps
    assert "completion" in caps

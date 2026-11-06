"""Ollama /api/show reports context and output-token limits (#2104)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from daari.config.settings import Settings
from daari.router.router import AppContext
from daari.server.app import create_app

OLLAMA_DOC = Path("docs/developer/guides/backends/ollama.md")


def _client(settings: Settings | None = None) -> TestClient:
    settings = settings or Settings()
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return TestClient(app)


def test_show_includes_context_length_from_routing_windows():
    settings = Settings()
    settings.routing.context_windows = {"L3": 8192, "L4": 32768, "L5": 131072}
    settings.models.l3 = "llama3.2:3b"
    body = _client(settings).post("/api/show", json={"model": "llama3.2:3b"}).json()
    info = body["model_info"]
    assert info["general.architecture"] == "daari-router"
    assert info["daari-router.context_length"] == 8192
    assert body["details"]["context_length"] == 8192
    assert "num_ctx" in body["parameters"]
    assert "8192" in body["parameters"]


def test_show_omits_context_length_when_window_unknown():
    settings = Settings()
    settings.routing.context_windows = {"L3": 8192}
    settings.models.l3 = "llama3.2:3b"
    settings.models.l4 = "unknown-mid:7b"
    body = _client(settings).post("/api/show", json={"model": "unknown-mid:7b"}).json()
    info = body["model_info"]
    assert "daari-router.context_length" not in info
    assert "context_length" not in body["details"]
    assert "num_ctx" not in (body.get("parameters") or "")


def test_show_virtual_model_uses_routed_target_window():
    settings = Settings()
    settings.routing.context_windows = {"L3": 8192, "L4": 32768, "L5": 131072}
    settings.models.l4 = "llama3.1:8b"
    settings.routing.virtual_models = {"code-router": ["llama3.1:8b"]}
    body = _client(settings).post("/api/show", json={"model": "code-router"}).json()
    assert body["model_info"]["daari-router.context_length"] == 32768
    assert body["details"]["context_length"] == 32768


def test_show_daari_uses_largest_known_window():
    settings = Settings()
    settings.routing.context_windows = {"L3": 8192, "L4": 32768, "L5": 131072}
    body = _client(settings).post("/api/show", json={"model": "daari"}).json()
    assert body["model_info"]["daari-router.context_length"] == 131072


def test_show_includes_max_output_when_catalog_knows():
    """Anthropic Haiku 5.5 publishes max_output_tokens=128000 (#1520 / #2104)."""
    settings = Settings()
    settings.frontier.model = "claude-haiku-5-5"
    settings.frontier.providers = []
    # Advertise the frontier id on the facade via virtual model → frontier target.
    settings.routing.virtual_models = {"haiku-proxy": ["claude-haiku-5-5"]}
    body = _client(settings).post("/api/show", json={"model": "haiku-proxy"}).json()
    assert body["model_info"]["daari-router.max_output_tokens"] == 128_000
    assert body["max_output_tokens"] == 128_000
    assert "num_predict" in body["parameters"]
    assert "128000" in body["parameters"]


def test_tags_and_show_stay_consistent_on_capabilities():
    settings = Settings()
    settings.models.l3 = "llama3.2:3b"
    client = _client(settings)
    tags = {m["name"]: m for m in client.get("/api/tags").json()["models"]}
    show = client.post("/api/show", json={"model": "llama3.2:3b"}).json()
    assert tags["llama3.2:3b"]["capabilities"] == show["capabilities"]
    assert show["renderer"] == ""
    assert show["parser"] == ""
    assert show["template_source"] == "model"


def test_docs_mention_show_limits():
    text = OLLAMA_DOC.read_text()
    assert "/api/show" in text
    assert "context_length" in text
    assert "daari-router.context_length" in text

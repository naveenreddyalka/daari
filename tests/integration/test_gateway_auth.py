"""Gateway API-key auth for tunnel exposure (issue #86)."""

from __future__ import annotations

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from daari.cli.setup_actions import ensure_server_api_key
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app

CHAT_PAYLOAD = {
    "model": "daari",
    "messages": [{"role": "user", "content": "auth smoke"}],
}


@pytest.fixture
def secured_app(settings):
    settings.server.api_key = "sekret-key"
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _mock_execute(app):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="authorized answer",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    app.state.ctx.router.ollama.execute = fake_execute


@pytest.mark.asyncio
async def test_missing_key_rejected(secured_app):
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT_PAYLOAD)
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "authentication_error"


@pytest.mark.asyncio
async def test_wrong_key_rejected(secured_app):
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT_PAYLOAD,
            headers={"Authorization": "Bearer wrong"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bearer_key_accepted(secured_app):
    _mock_execute(secured_app)
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT_PAYLOAD,
            headers={"Authorization": "Bearer sekret-key"},
        )
    assert response.status_code == 200
    assert "authorized answer" in response.text


@pytest.mark.asyncio
async def test_x_api_key_accepted(secured_app):
    """Anthropic-protocol clients (Claude Code) send x-api-key, not Bearer."""
    _mock_execute(secured_app)
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json=CHAT_PAYLOAD,
            headers={"x-api-key": "sekret-key"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_endpoints_stay_open(secured_app):
    transport = ASGITransport(app=secured_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        anthropic_health = await client.get("/v1/messages/health")
    assert health.status_code == 200
    assert anthropic_health.status_code == 200


@pytest.mark.asyncio
async def test_default_config_requires_no_auth(settings):
    """Empty api_key (the default) keeps the gateway open for local use."""
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    _mock_execute(application)
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=CHAT_PAYLOAD)
    assert response.status_code == 200


class TestEnsureServerApiKey:
    def test_generates_and_persists_key(self, settings, tmp_path):
        config_path = tmp_path / "config.yaml"
        settings.server.api_key = ""
        key, generated = ensure_server_api_key(settings, config_path=config_path)
        assert generated is True
        assert len(key) >= 24
        assert settings.server.api_key == key
        stored = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert stored["server"]["api_key"] == key

    def test_existing_key_untouched(self, settings, tmp_path):
        config_path = tmp_path / "config.yaml"
        settings.server.api_key = "already-set"
        key, generated = ensure_server_api_key(settings, config_path=config_path)
        assert generated is False
        assert key == "already-set"
        assert not config_path.exists()

    def test_preserves_other_config_keys(self, settings, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.safe_dump({"models": {"l3": "custom:3b"}}), encoding="utf-8")
        settings.server.api_key = ""
        key, generated = ensure_server_api_key(settings, config_path=config_path)
        assert generated is True
        stored = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert stored["models"]["l3"] == "custom:3b"
        assert stored["server"]["api_key"] == key

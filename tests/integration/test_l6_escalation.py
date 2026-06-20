from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.fixture
def frontier_settings(tmp_path):
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": "http://127.0.0.1:11434"},
            "cache": {"l0": {"enabled": True, "path": str(tmp_path / "l0")}},
            "frontier": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-4o-mini",
                "confidence_threshold": 0.7,
                "base_url": "https://api.openai.com/v1",
            },
        }
    )


@pytest.fixture
def frontier_app(frontier_settings, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key")
    application = create_app(frontier_settings)
    application.state.ctx = AppContext.from_settings(frontier_settings)
    return application


@pytest.mark.asyncio
async def test_l6_escalation_via_gateway(frontier_app, monkeypatch):
    async def fake_l3(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="no",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    async def fake_l6(
        request: InternalRequest,
        *,
        escalated_from: str,
        local_confidence: float,
    ) -> InternalResponse:
        return InternalResponse(
            content="Frontier answer with enough detail for the user.",
            model="gpt-4o-mini",
            daari_meta=DaariMeta(
                tier="L6",
                executor="frontier",
                provider_id="openai",
                latency_ms=50,
                model="gpt-4o-mini",
                confidence=local_confidence,
                escalated_from=escalated_from,
            ),
        )

    monkeypatch.setattr(frontier_app.state.ctx.router.ollama, "execute", fake_l3)
    monkeypatch.setattr(frontier_app.state.ctx.router.frontier, "execute", fake_l6)

    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "hard question"}],
    }

    transport = ASGITransport(app=frontier_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=payload)
        stats = await client.get("/v1/daari/stats")

    body = response.json()
    assert response.status_code == 200
    assert body["daari_meta"]["tier"] == "L6"
    assert body["daari_meta"]["escalated_from"] == "L3"
    assert stats.json()["tiers"]["L6"]["count"] == 1

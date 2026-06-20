"""Optional live Ollama integration — skipped unless OLLAMA_HOST is set."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.router import AppContext
from daari.server.app import create_app

OLLAMA_HOST = os.environ.get("OLLAMA_HOST")


@pytest.fixture
def live_settings(tmp_path):
    from daari.config.settings import Settings

    base_url = OLLAMA_HOST or "http://127.0.0.1:11434"
    return Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": "llama3.2:3b"},
            "ollama": {"base_url": base_url},
            "cache": {
                "l0": {"enabled": True, "path": str(tmp_path / "l0")},
                "l1": {"enabled": True, "path": str(tmp_path / "l1")},
            },
            "context": {"enabled": True, "path": str(tmp_path / "context")},
        }
    )


@pytest.fixture
def live_app(live_settings):
    application = create_app(live_settings)
    application.state.ctx = AppContext.from_settings(live_settings)
    return application


@pytest.mark.integration
@pytest.mark.skipif(not OLLAMA_HOST, reason="Set OLLAMA_HOST to run live Ollama tests")
@pytest.mark.asyncio
async def test_live_ollama_chat_and_cache(live_app):
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "Reply with exactly: pong"}],
    }

    transport = ASGITransport(app=live_app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=120.0) as client:
        first = await client.post("/v1/chat/completions", json=payload)
        second = await client.post("/v1/chat/completions", json=payload)

    assert first.status_code == 200, first.text
    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.json()["daari_meta"]["tier"] == "L0"

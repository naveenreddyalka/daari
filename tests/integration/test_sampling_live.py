"""Sampling parameters change real generation (issue #161).

`tests/unit/test_sampling_end_to_end.py` proves the values reach the wire against a
mock. These prove the model then acts on them, which is the thing a client actually
asked for. Streaming, vision, and embeddings live coverage lives in
`test_client_path_live.py` (issue #191). Skipped unless OLLAMA_HOST is set.
"""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from daari.router.router import AppContext
from daari.server.app import create_app

OLLAMA_HOST = os.environ.get("OLLAMA_HOST")
MODEL = "llama3.2:3b"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not OLLAMA_HOST, reason="Set OLLAMA_HOST to run live Ollama tests"),
]


@pytest.fixture
def live_app(tmp_path):
    from daari.config.settings import Settings

    settings = Settings.model_validate(
        {
            "server": {"host": "127.0.0.1", "port": 11435},
            "models": {"l3": MODEL},
            "ollama": {"base_url": OLLAMA_HOST or "http://127.0.0.1:11434"},
            # Caching off: these assertions are about generation, and a hit would
            # replay an answer produced under different parameters.
            "cache": {"l0": {"enabled": False}, "l1": {"enabled": False}},
            "context": {"enabled": False, "path": str(tmp_path / "context")},
            "routing": {"max_tier_for_chat": "L3"},
        }
    )
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


async def _chat(app, **overrides):
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Count slowly from one to twenty in words."}],
        **overrides,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as client:
        response = await client.post(
            "/v1/chat/completions", json=payload, headers={"X-Daari-Meta": "true"}
        )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_max_tokens_actually_truncates(live_app):
    """The cap the client sent has to bind the model, not just the payload."""
    capped = await _chat(live_app, max_tokens=8)
    text = capped["choices"][0]["message"]["content"]

    assert capped["usage"]["completion_tokens"] <= 8, text
    assert "twenty" not in text.lower(), "an 8-token answer cannot have finished counting"


@pytest.mark.asyncio
async def test_a_shared_seed_reproduces_the_answer(live_app):
    """Determinism is the whole point of exposing seed."""
    first = await _chat(live_app, seed=1234, max_tokens=40)
    second = await _chat(live_app, seed=1234, max_tokens=40)

    assert (
        first["choices"][0]["message"]["content"] == second["choices"][0]["message"]["content"]
    )


@pytest.mark.asyncio
async def test_a_stop_sequence_ends_generation(live_app):
    """Ollama matches stop strings case-sensitively, so send both spellings."""
    answer = await _chat(live_app, stop=["Five", "five"], seed=7, max_tokens=60)
    text = answer["choices"][0]["message"]["content"]

    assert "five" not in text.lower(), text
    assert "our" in text.lower(), "it should have counted at least to four first"


@pytest.mark.asyncio
async def test_json_mode_returns_parseable_json(live_app):
    import json

    transport = ASGITransport(app=live_app)
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Give me an object with a name field."}],
        "response_format": {"type": "json_object"},
        "max_tokens": 80,
    }
    async with AsyncClient(transport=transport, base_url="http://test", timeout=180.0) as client:
        response = await client.post(
            "/v1/chat/completions", json=payload, headers={"X-Daari-Meta": "true"}
        )

    assert response.status_code == 200, response.text
    body = json.loads(response.json()["choices"][0]["message"]["content"])
    assert isinstance(body, dict)

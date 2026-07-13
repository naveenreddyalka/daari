"""Ollama-compatible facade integration tests (issue #81)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _fake_execute(content: str = "hello from daari"):
    async def execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=content,
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=5,
            ),
        )

    return execute


def _mock_stream_executor(monkeypatch, router, content: str) -> None:
    """Route every stream tier to a fake executor emitting Ollama-style events."""

    class FakeStreamExecutor:
        default_model = "llama3.2:3b"

        async def stream(self, request: InternalRequest):
            yield {"message": {"role": "assistant", "content": content}, "done": False}
            yield {"message": {"role": "assistant", "content": ""}, "done": True}

    fake = FakeStreamExecutor()
    monkeypatch.setattr(router, "_executor_for_tier", lambda tier: fake)


@pytest.mark.asyncio
async def test_tags_lists_daari_and_tier_models(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/tags")

    assert response.status_code == 200
    names = [entry["name"] for entry in response.json()["models"]]
    assert "daari" in names
    assert app.state.ctx.settings.models.l3 in names


@pytest.mark.asyncio
async def test_version_and_show_and_ps(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        version = await client.get("/api/version")
        show = await client.post("/api/show", json={"model": "daari"})
        ps = await client.get("/api/ps")

    assert version.status_code == 200
    assert "version" in version.json()
    assert show.status_code == 200
    assert "daari" in show.json()["modelfile"]
    assert ps.status_code == 200
    assert ps.json() == {"models": []}


@pytest.mark.asyncio
async def test_chat_non_stream_routes_through_daari(app, monkeypatch):
    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", _fake_execute())
    payload = {
        "model": "daari",
        "stream": False,
        "messages": [{"role": "user", "content": "ollama facade smoke"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "hello from daari"
    assert body["done"] is True
    assert body["daari_meta"]["tier"] == "L3"


@pytest.mark.asyncio
async def test_chat_stream_emits_ndjson_lines(app, monkeypatch):
    _mock_stream_executor(monkeypatch, app.state.ctx.router, "streamed body text")
    payload = {
        "model": "daari",
        "messages": [{"role": "user", "content": "ollama facade stream smoke"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(line) for line in response.text.strip().splitlines()]
    assert lines, "expected at least one NDJSON line"
    content = "".join(line["message"]["content"] for line in lines if not line["done"])
    assert "streamed body text" in content
    final = lines[-1]
    assert final["done"] is True
    assert final["done_reason"] == "stop"


@pytest.mark.asyncio
async def test_chat_stream_default_true(app, monkeypatch):
    """Native Ollama clients omit `stream` and expect NDJSON streaming."""
    _mock_stream_executor(monkeypatch, app.state.ctx.router, "default stream body")
    payload = {
        "model": "daari",
        "messages": [{"role": "user", "content": "default stream check"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json=payload)

    assert response.headers["content-type"].startswith("application/x-ndjson")


@pytest.mark.asyncio
async def test_chat_records_client_id_in_ledger(app, monkeypatch):
    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", _fake_execute())
    payload = {
        "model": "daari",
        "stream": False,
        "messages": [{"role": "user", "content": "client attribution check"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/chat", json=payload, headers={"X-Daari-Client-Id": "intellij"}
        )

    assert response.status_code == 200
    ledger = app.state.ctx.router.usage_ledger
    if ledger is not None and ledger.enabled:
        clients = {row["client_id"] for row in ledger.by_client()}
        assert "intellij" in clients


@pytest.mark.asyncio
async def test_anthropic_system_field_reaches_router(app, monkeypatch):
    """Claude Code sends the system prompt top-level; it must not be dropped."""
    seen: dict[str, list] = {}

    async def capture_execute(request: InternalRequest) -> InternalResponse:
        seen["messages"] = list(request.messages)
        return InternalResponse(
            content="ack",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", capture_execute)
    payload = {
        "model": "daari",
        "max_tokens": 64,
        "system": "You are the daari test system prompt.",
        "messages": [{"role": "user", "content": "anthropic system field check"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/messages", json=payload)

    assert response.status_code == 200
    roles = [message.role for message in seen["messages"]]
    assert roles[0] == "system"
    assert "daari test system prompt" in (seen["messages"][0].content or "")


@pytest.mark.asyncio
async def test_anthropic_system_blocks_accepted(app, monkeypatch):
    """system can also arrive as a list of content blocks."""
    seen: dict[str, list] = {}

    async def capture_execute(request: InternalRequest) -> InternalResponse:
        seen["messages"] = list(request.messages)
        return InternalResponse(
            content="ack",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=1),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", capture_execute)
    payload = {
        "model": "daari",
        "max_tokens": 64,
        "system": [{"type": "text", "text": "block system prompt"}],
        "messages": [{"role": "user", "content": "anthropic system blocks check"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/messages", json=payload)

    assert response.status_code == 200
    assert seen["messages"][0].role == "system"
    assert "block system prompt" in (seen["messages"][0].content or "")

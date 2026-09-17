"""daari_meta.agent_turn for ADR-0004 / #604."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.cache.exact import ExactCache
from daari.cache.semantic import SemanticCache
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.observability.metrics import Metrics
from daari.router.router import OllamaExecutor, Router
from daari.server.app import create_app
from daari.router.router import AppContext
from tests.conftest import NoopEmbedder, mock_all_ollama_executors


@pytest.mark.asyncio
async def test_route_sets_agent_turn_true_for_tools(tmp_path):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="tool-aware answer",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    executor.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=executor,
        metrics=Metrics(),
    )
    request = InternalRequest(
        messages=[Message(role="user", content="call a tool")],
        model="daari",
        tools=[{"type": "function", "function": {"name": "run", "parameters": {}}}],
    )
    result = await router.route(request)
    assert result.daari_meta.agent_turn is True


@pytest.mark.asyncio
async def test_route_omits_agent_turn_for_plain_chat(tmp_path):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="plain answer",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    executor.execute = fake_execute  # type: ignore[method-assign]
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=executor,
        metrics=Metrics(),
    )
    result = await router.route(
        InternalRequest(messages=[Message(role="user", content="hello")], model="daari")
    )
    assert result.daari_meta.agent_turn is None


@pytest.mark.asyncio
async def test_openai_response_includes_agent_turn_when_true(settings, monkeypatch):
    settings.observability.prometheus = False
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)

    body = {
        "model": "daari",
        "messages": [{"role": "user", "content": "hi"}],
        "tools": [{"type": "function", "function": {"name": "run", "parameters": {}}}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        with_meta = await client.post(
            "/v1/chat/completions",
            json=body,
            headers={"X-Daari-Meta": "true", "X-Daari-Tools": "passthrough"},
        )
        plain = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "hi"}]},
            headers={"X-Daari-Meta": "true"},
        )

    assert with_meta.status_code == 200
    assert with_meta.json()["daari_meta"]["agent_turn"] is True
    assert plain.status_code == 200
    assert "agent_turn" not in plain.json().get("daari_meta", {})

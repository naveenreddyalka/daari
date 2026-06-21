"""Gateway + router + cache integration (mocked Ollama)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.policy.engine import PolicyResult
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.tools.shell import ShellResult


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_full_stack_l0_after_l3(app, monkeypatch):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="from-ollama",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=50,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "integration smoke"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload)
        second = await client.post("/v1/chat/completions", json=payload)
        stats = await client.get("/v1/daari/stats")

    assert first.status_code == 200
    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.json()["daari_meta"]["tier"] == "L0"
    assert stats.json()["total_requests"] == 2


@pytest.mark.asyncio
async def test_no_cache_header_skips_l0(app, monkeypatch):
    call_count = 0

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal call_count
        call_count += 1
        return InternalResponse(
            content=f"hit-{call_count}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "no cache please"}],
    }
    headers = {"X-Daari-No-Cache": "true"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload, headers=headers)
        second = await client.post("/v1/chat/completions", json=payload, headers=headers)

    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.json()["daari_meta"]["tier"] == "L3"
    assert call_count == 2


@pytest.mark.asyncio
async def test_reload_caches_endpoint_refreshes_app_context_handles(app, monkeypatch):
    monkeypatch.setattr(
        app.state.ctx,
        "reload_cache_handles",
        lambda: {"reloaded": True, "l0_path": "/tmp/l0", "l1_path": "/tmp/l1", "ccs_path": "/tmp/ccs"},
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/daari/reload-caches")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["reloaded"] is True
    assert payload["l0_path"] == "/tmp/l0"


@pytest.mark.asyncio
async def test_org_learning_sync_endpoint_refreshes_profile(app, monkeypatch):
    async def fake_sync() -> bool:
        app.state.ctx.router.model_preference = "accuracy"
        app.state.ctx.router.confidence_threshold = 0.81
        return True

    monkeypatch.setattr(app.state.ctx, "sync_org_learning_profile_once", fake_sync)
    app.state.ctx.org_learning_client = object()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/org-learning/sync")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["changed"] is True
    assert payload["routing"]["prefer"] == "accuracy"
    assert payload["routing"]["confidence_threshold"] == 0.81


@pytest.mark.asyncio
async def test_anthropic_messages_adapter_routes_to_daari(app, monkeypatch):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="anthropic-compatible-response",
            model="claude-sonnet-4-20250514",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama:l3",
                latency_ms=7,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "Explain this file."}],
                "max_tokens": 256,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "message"
    assert payload["content"][0]["text"] == "anthropic-compatible-response"
    assert payload["daari_meta"]["tier"] == "L3"


@pytest.mark.asyncio
async def test_stream_chunks_include_daari_meta(app, monkeypatch):
    async def fake_stream(_request: InternalRequest):
        yield {"message": {"content": "Hello"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "llama3.2:3b",
                "messages": [{"role": "user", "content": "stream this"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    first_payload = json.loads(lines[0].replace("data: ", ""))
    assert first_payload["daari_meta"]["tier"] in {"L3", "L4", "L5"}
    assert first_payload["daari_meta"]["stream"] is True


@pytest.mark.asyncio
async def test_anthropic_streaming_events(app, monkeypatch):
    async def fake_stream(_request: InternalRequest):
        yield {"message": {"content": "Hello "}}
        yield {"message": {"content": "world"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "stream this"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    body = response.text
    assert "event: message_start" in body
    assert "event: content_block_start" in body
    assert "event: content_block_delta" in body
    assert "Hello " in body
    assert "world" in body
    assert "event: message_stop" in body


@pytest.mark.asyncio
async def test_mcp_gateway_query_routes(app, monkeypatch):
    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="mcp-routed",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/mcp/query", json={"tool": "route", "input": "hello"})
    assert response.status_code == 200
    assert response.json()["result"]["content"] == "mcp-routed"


@pytest.mark.asyncio
async def test_mcp_tools_list_and_tools_call(app, monkeypatch):
    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="from-tools-call",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tools_list = await client.post("/v1/mcp/query", json={"tool": "tools/list"})
        tools_call = await client.post(
            "/v1/mcp/query",
            json={"tool": "tools/call", "args": {"name": "route", "arguments": {"input": "hello"}}},
        )

    assert tools_list.status_code == 200
    assert any(tool["name"] == "route" for tool in tools_list.json()["result"]["tools"])
    assert tools_call.status_code == 200
    assert tools_call.json()["result"]["name"] == "route"
    assert tools_call.json()["result"]["result"]["content"] == "from-tools-call"


@pytest.mark.asyncio
async def test_mcp_tools_call_schema_validation_error(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/mcp/query",
            json={"tool": "tools/call", "args": {"name": "route", "arguments": {"input": 123}}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert payload["result"]["error"]["code"] == "MCP_ERR_SCHEMA_VALIDATION"
    assert payload["result"]["error"]["details"][0]["code"] == "MCP_ERR_INVALID_ARGUMENT_TYPE"


@pytest.mark.asyncio
async def test_mcp_tools_call_missing_name_has_structured_error(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/mcp/query", json={"tool": "tools/call", "args": {}})
    assert response.status_code == 200
    assert response.json()["result"]["error"]["code"] == "MCP_ERR_MISSING_TOOL_NAME"


@pytest.mark.asyncio
async def test_router_integration_prefix_routes_before_l3(app, monkeypatch):
    async def fail_if_model_called(_request: InternalRequest) -> InternalResponse:
        raise AssertionError("model tier should not execute for integration-prefixed request")

    async def fake_sourcegraph(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="sourcegraph-result",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="Lt", executor="integration", provider_id="integration:sourcegraph"),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fail_if_model_called)
    sourcegraph_provider = app.state.ctx.providers.get("integration:sourcegraph")
    assert sourcegraph_provider is not None
    monkeypatch.setattr(sourcegraph_provider, "execute", fake_sourcegraph)

    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "@sourcegraph search auth middleware"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=payload, headers={"X-Daari-No-Cache": "true"})

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "sourcegraph-result"
    assert response.json()["daari_meta"]["provider_id"] == "integration:sourcegraph"


@pytest.mark.asyncio
async def test_router_gitlab_prefix_routes_before_l3(app, monkeypatch):
    async def fail_if_model_called(_request: InternalRequest) -> InternalResponse:
        raise AssertionError("model tier should not execute for integration-prefixed request")

    async def fake_gitlab(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="gitlab-result",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="Lt", executor="integration", provider_id="integration:gitlab"),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fail_if_model_called)
    gitlab_provider = app.state.ctx.providers.get("integration:gitlab")
    assert gitlab_provider is not None
    monkeypatch.setattr(gitlab_provider, "execute", fake_gitlab)

    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "@gitlab search auth middleware"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=payload, headers={"X-Daari-No-Cache": "true"})

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "gitlab-result"
    assert response.json()["daari_meta"]["provider_id"] == "integration:gitlab"


@pytest.mark.asyncio
async def test_anthropic_stream_falls_back_to_non_stream(app, monkeypatch):
    async def broken_stream(_request: InternalRequest):
        raise RuntimeError("stream broke")
        yield

    async def fallback_route(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="fallback-non-stream",
            model="claude-sonnet-4-20250514",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    monkeypatch.setattr(app.state.ctx.router, "stream_anthropic_events", broken_stream)
    monkeypatch.setattr(app.state.ctx.router, "route", fallback_route)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": "stream this"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    text = response.text
    assert "event: error" in text
    assert "stream_failed_fell_back_to_non_stream" in text
    assert "fallback-non-stream" in text


@pytest.mark.asyncio
async def test_lt_ask_response_includes_confirmation_prompt(app, monkeypatch):
    def fake_policy(command: str, *, confirmed: bool = False) -> PolicyResult:
        if confirmed:
            return PolicyResult(outcome="allow", reason="confirmed")
        return PolicyResult(outcome="ask", reason="needs confirmation")

    async def fake_shell(command: str, *, cwd: str | None = None) -> ShellResult:
        return ShellResult(command=command, output="confirmed-output", exit_code=0)

    monkeypatch.setattr(app.state.ctx.router.policy, "evaluate", fake_policy)
    monkeypatch.setattr(app.state.ctx.router.shell_executor, "run", fake_shell)

    payload = {"model": "llama3.2:3b", "messages": [{"role": "user", "content": "run git status"}]}
    headers = {"X-Daari-No-Cache": "true"}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload, headers=headers)
        second = await client.post(
            "/v1/chat/completions",
            json=payload,
            headers={**headers, "X-Daari-Confirm": "yes"},
        )

    first_body = first.json()
    second_body = second.json()
    assert first.status_code == 200
    assert first_body["daari_meta"]["policy"] == "ask"
    assert "X-Daari-Confirm: yes" in first_body["daari_meta"]["confirmation_prompt"]
    assert second_body["daari_meta"]["policy"] == "allow"

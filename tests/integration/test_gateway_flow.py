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
from tests.conftest import META_HEADERS, MOCK_MODEL_CONTENT, mock_all_ollama_executors


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
        first = await client.post("/v1/chat/completions", json=payload, headers=META_HEADERS)
        second = await client.post("/v1/chat/completions", json=payload, headers=META_HEADERS)
        stats = await client.get("/v1/daari/stats")

    assert first.status_code == 200
    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.json()["daari_meta"]["tier"] == "L0"
    assert stats.json()["total_requests"] == 2


@pytest.mark.asyncio
async def test_openai_array_content_accepted(app, monkeypatch):
    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="4",
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
        "model": "daari",
        "stream": True,
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": [{"type": "text", "text": "What is 2 plus 2?"}]},
        ],
        "max_tokens": 100,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    assert "data:" in response.text


@pytest.mark.asyncio
async def test_no_cache_header_skips_l0(app, monkeypatch):
    call_count = 0

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        nonlocal call_count
        call_count += 1
        return InternalResponse(
            content=f"hit-{call_count} with enough length",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "no cache please"}],
    }
    headers = {"X-Daari-No-Cache": "true", **META_HEADERS}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload, headers=headers)
        second = await client.post("/v1/chat/completions", json=payload, headers=headers)

    assert first.json()["daari_meta"]["tier"] == "L3"
    assert second.json()["daari_meta"]["tier"] == "L3"
    assert call_count == 2


@pytest.mark.asyncio
async def test_cursor_tools_stripped_returns_text(app, monkeypatch):
    async def fake_stream(request: InternalRequest):
        assert request.tools is None
        yield {"message": {"content": "4"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    tools = [
        {
            "type": "function",
            "function": {
                "name": f"tool_{index}",
                "description": "demo",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for index in range(18)
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "stream_options": {"include_usage": True},
                "messages": [
                    {"role": "system", "content": "You are a coding assistant with tools."},
                    {"role": "user", "content": [{"type": "text", "text": "What is 2 plus 2?"}]},
                    {"role": "user", "content": [{"type": "text", "text": "What is 2 plus 2?"}]},
                ],
                "tools": tools,
            },
        )

    assert response.status_code == 200
    assert "4" in response.text


@pytest.mark.asyncio
async def test_no_tools_hint_leads_and_neutralizes_tool_prompt(app, monkeypatch):
    """Issue #1: stripped-tools requests must lead with an explicit no-tools system message."""
    from daari.gateway.openai import NO_TOOLS_HINT

    seen_requests: list[InternalRequest] = []

    async def fake_stream(request: InternalRequest):
        seen_requests.append(request)
        yield {"message": {"content": "plain text answer"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    tools = [
        {
            "type": "function",
            "function": {
                "name": f"tool_{index}",
                "description": "demo",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for index in range(18)
    ]
    # Multi-turn Cursor-style payload whose system prompt advertises tools.
    body = {
        "model": "daari",
        "stream": True,
        "messages": [
            {"role": "system", "content": "You are a coding agent. Use the read_file and shell tools when needed."},
            {"role": "user", "content": [{"type": "text", "text": "what is two plus two?"}]},
            {"role": "assistant", "content": "Four."},
            {"role": "user", "content": [{"type": "text", "text": "yes go ahead"}]},
        ],
        "tools": tools,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=body)
        second = await client.post("/v1/chat/completions", json=body)

    assert first.status_code == 200 and second.status_code == 200
    for request in seen_requests:
        assert request.tools is None
        # The hint must be the FIRST system instruction the model sees.
        assert request.messages[0].role == "system"
        assert NO_TOOLS_HINT in (request.messages[0].content or "")
        assert "NO tools available" in request.messages[0].content
        # Idempotent: exactly one message carries the hint even on repeat requests.
        hint_count = sum(1 for m in request.messages if NO_TOOLS_HINT in (m.content or ""))
        assert hint_count == 1
        # Original client system prompt is preserved after the hint.
        assert any("read_file" in (m.content or "") for m in request.messages if m.role == "system")


@pytest.mark.asyncio
async def test_cursor_input_text_content_returns_text(app, monkeypatch):
    async def fake_stream(request: InternalRequest):
        assert any(message.role == "user" for message in request.messages)
        yield {"message": {"content": "4"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    tools = [
        {
            "type": "function",
            "function": {
                "name": f"tool_{index}",
                "description": "demo",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for index in range(18)
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [
                    {"role": "system", "content": "You are a coding assistant."},
                    {"role": "user", "content": [{"type": "input_text", "text": "What is 2 plus 2?"}]},
                    {"role": "user", "content": [{"type": "input_text", "text": "What is 2 plus 2?"}]},
                ],
                "tools": tools,
            },
        )

    assert response.status_code == 200
    assert "4" in response.text


@pytest.mark.asyncio
async def test_stream_falls_back_to_l3_when_l4_unavailable(app, monkeypatch):
    seen_models: list[str] = []

    async def l4_stream(_request: InternalRequest):
        raise RuntimeError("404 Not Found")
        yield {"done": True}  # pragma: no cover

    async def l3_stream(request: InternalRequest):
        seen_models.append(request.model)
        yield {"message": {"content": "fallback-text"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama_l4, "stream", l4_stream)
    monkeypatch.setattr(app.state.ctx.router.ollama_l3, "stream", l3_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [
                    {"role": "system", "content": "sys"},
                    {"role": "user", "content": "short"},
                    {"role": "user", "content": " ".join(["word"] * 260)},
                ],
            },
        )

    assert response.status_code == 200
    assert "fallback-text" in response.text
    assert seen_models == ["llama3.2:3b"]


@pytest.mark.asyncio
async def test_stream_sanitizes_assistant_tool_calls(app, monkeypatch):
    seen_messages: list[InternalRequest] = []

    async def fake_stream(request: InternalRequest):
        seen_messages.append(request.model_copy(deep=True))
        yield {"message": {"content": "done"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "grep",
                "description": "demo",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [
                    {"role": "user", "content": "run tool"},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "1",
                                "type": "function",
                                "function": {"name": "grep", "arguments": "{}"},
                            }
                        ],
                    },
                    {"role": "user", "content": "now what?"},
                ],
                "tools": tools,
            },
        )

    assert response.status_code == 200
    assert "done" in response.text
    assert seen_messages
    assert all(message.tool_calls is None for message in seen_messages[0].messages)
    assert any("grep" in (message.content or "") for message in seen_messages[0].messages)


@pytest.mark.asyncio
async def test_openai_models_list(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/models")
        model_response = await client.get("/v1/models/daari")

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    assert any(item["id"] == "daari" for item in payload["data"])
    assert model_response.status_code == 200
    assert model_response.json()["id"] == "daari"


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
async def test_stream_chunks_are_openai_compatible(app, monkeypatch):
    async def fake_stream(_request: InternalRequest):
        yield {"message": {"content": "Hello"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "stream this"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    first_payload = json.loads(lines[0].replace("data: ", ""))
    assert first_payload["model"] == "daari"
    assert first_payload["choices"][0]["delta"]["role"] == "assistant"
    assert "daari_meta" not in first_payload
    content_payload = json.loads(lines[1].replace("data: ", ""))
    assert content_payload["choices"][0]["delta"]["content"] == "Hello"
    assert content_payload["model"] == "daari"


@pytest.mark.asyncio
async def test_non_stream_includes_daari_meta(app, monkeypatch):
    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama:l3",
                latency_ms=1,
            ),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False,
            },
            headers={"X-Daari-Meta": "true"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["model"] == "daari"
    assert payload["usage"]["total_tokens"] >= 1
    assert payload["daari_meta"]["tier"] == "L3"


@pytest.mark.asyncio
async def test_stream_include_usage_chunk(app, monkeypatch):
    async def fake_stream(_request: InternalRequest):
        yield {"message": {"content": "Hi"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
                "stream_options": {"include_usage": True},
            },
        )

    assert response.status_code == 200
    lines = [line for line in response.text.splitlines() if line.startswith("data: ") and line != "data: [DONE]"]
    usage_payload = json.loads(lines[-1].replace("data: ", ""))
    assert usage_payload["choices"] == []
    assert usage_payload["usage"]["total_tokens"] >= 1


@pytest.mark.asyncio
async def test_stream_daari_model_alias_uses_ollama_default(app, monkeypatch):
    seen_models: list[str] = []

    async def fake_stream(request: InternalRequest):
        seen_models.append(request.model)
        yield {"message": {"content": "4"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": [{"type": "text", "text": "2+2"}]}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    assert seen_models == ["llama3.2:3b"]
    assert "4" in response.text


@pytest.mark.asyncio
async def test_stream_error_payload_is_valid_json(app, monkeypatch):
    async def broken_stream(_request: InternalRequest):
        raise RuntimeError("Client error '404 Not Found'\nFor more information")
        yield {"done": True}  # pragma: no cover

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", broken_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "ping"}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    error_lines = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ") and line != "data: [DONE]"
    ]
    error_payload = json.loads(error_lines[-1])
    assert "error" in error_payload
    assert "404 Not Found" in error_payload["error"]


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
            content="mcp-routed-response",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/mcp/query", json={"tool": "route", "input": "hello"})
    assert response.status_code == 200
    assert response.json()["result"]["content"] == "mcp-routed-response"


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
        response = await client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"X-Daari-No-Cache": "true", **META_HEADERS},
        )

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
        response = await client.post(
            "/v1/chat/completions",
            json=payload,
            headers={"X-Daari-No-Cache": "true", **META_HEADERS},
        )

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
    headers = {"X-Daari-No-Cache": "true", **META_HEADERS}
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

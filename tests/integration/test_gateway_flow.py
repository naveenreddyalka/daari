"""Gateway + router + cache integration (mocked Ollama)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
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


def _demo_tools(count: int = 1) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": f"read_file_{index}" if count > 1 else "read_file",
                "description": "demo",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for index in range(count)
    ]


def _agent_history_messages() -> list[dict]:
    return [
        {"role": "system", "content": "You are a coding agent with tools."},
        {"role": "user", "content": "read a.py"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_abc123",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                }
            ],
        },
        {"role": "tool", "content": "print('hello')"},
    ]


@pytest.mark.asyncio
async def test_agent_flow_with_tool_history_passes_tools_through(app, monkeypatch):
    """Issue #2: tool history means agent mode — tools reach the executor untouched."""
    from daari.gateway.openai import NO_TOOLS_HINT

    seen: list[InternalRequest] = []

    async def fake_stream(request: InternalRequest):
        seen.append(request)
        yield {"message": {"content": "the file prints hello"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    tools = _demo_tools()
    body = {
        "model": "daari",
        "stream": True,
        "messages": _agent_history_messages(),
        "tools": tools,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    request = seen[0]
    assert request.tools == tools
    assert all(NO_TOOLS_HINT not in (m.content or "") for m in request.messages)
    assert any(m.role == "tool" for m in request.messages)
    assert any(m.tool_calls for m in request.messages)


@pytest.mark.asyncio
async def test_tools_header_passthrough_overrides_fresh_request(app, monkeypatch):
    """Issue #2: X-Daari-Tools: passthrough forces agent mode without tool history."""
    seen: list[InternalRequest] = []

    async def fake_stream(request: InternalRequest):
        seen.append(request)
        yield {"message": {"content": "ok"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    tools = _demo_tools()
    body = {
        "model": "daari",
        "stream": True,
        "messages": [
            {"role": "system", "content": "Agent."},
            {"role": "user", "content": "read a.py"},
        ],
        "tools": tools,
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions", json=body, headers={"X-Daari-Tools": "passthrough"}
        )

    assert response.status_code == 200
    assert seen[0].tools == tools


@pytest.mark.asyncio
async def test_tools_header_strip_overrides_agent_history(app, monkeypatch):
    """Issue #2: X-Daari-Tools: strip forces Ask mode even with tool history."""
    from daari.gateway.openai import NO_TOOLS_HINT

    seen: list[InternalRequest] = []

    async def fake_stream(request: InternalRequest):
        seen.append(request)
        yield {"message": {"content": "plain text"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    body = {
        "model": "daari",
        "stream": True,
        "messages": _agent_history_messages(),
        "tools": _demo_tools(),
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions", json=body, headers={"X-Daari-Tools": "strip"}
        )

    assert response.status_code == 200
    request = seen[0]
    assert request.tools is None
    assert NO_TOOLS_HINT in (request.messages[0].content or "")
    # Tool protocol fields sanitized away for the local model.
    assert all(not m.tool_calls for m in request.messages)
    assert all(m.role != "tool" for m in request.messages)


@pytest.mark.asyncio
async def test_stream_emits_openai_tool_call_deltas(app, monkeypatch):
    """Issue #2: agent-mode streams emit OpenAI tool_calls deltas, not JSON text dumps."""

    async def fake_stream(request: InternalRequest):
        # Ollama-native tool call shape: arguments as a dict, no id.
        yield {
            "message": {
                "content": "",
                "tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "a.py"}}}],
            }
        }
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    body = {
        "model": "daari",
        "stream": True,
        "messages": _agent_history_messages(),
        "tools": _demo_tools(),
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=body)

    assert response.status_code == 200
    tool_call_delta = None
    finish_reasons = []
    for line in response.text.splitlines():
        if not line.startswith("data: ") or line == "data: [DONE]":
            continue
        chunk = json.loads(line[len("data: "):])
        for choice in chunk.get("choices", []):
            if choice.get("finish_reason"):
                finish_reasons.append(choice["finish_reason"])
            delta = choice.get("delta", {})
            if delta.get("tool_calls"):
                tool_call_delta = delta["tool_calls"]

    assert tool_call_delta is not None, f"no tool_calls delta in stream: {response.text}"
    call = tool_call_delta[0]
    assert call["index"] == 0
    assert call["type"] == "function"
    assert call["id"].startswith("call_")
    assert call["function"]["name"] == "read_file"
    assert json.loads(call["function"]["arguments"]) == {"path": "a.py"}
    assert "tool_calls" in finish_reasons


@pytest.mark.asyncio
async def test_stream_l0_cache_hit_on_repeat(app, monkeypatch):
    """Issue #13: identical non-agent streams are served from L0 on repeat."""
    calls = 0

    async def fake_stream(request: InternalRequest):
        nonlocal calls
        calls += 1
        yield {"message": {"content": "a cache stores answers "}}
        yield {"message": {"content": "for reuse"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    body = {
        "model": "daari",
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": [{"role": "user", "content": "what is a cache?"}],
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=body)
        second = await client.post("/v1/chat/completions", json=body)
        stats = (await client.get("/v1/daari/stats")).json()

    assert first.status_code == 200 and second.status_code == 200
    assert calls == 1, "second stream should be served from L0 without hitting the executor"
    assert "a cache stores answers" in second.text
    assert "data: [DONE]" in second.text
    assert '"finish_reason": "stop"' in second.text or '"finish_reason":"stop"' in second.text
    assert stats["tiers"].get("L0", {}).get("cache_hits") == 1
    assert stats["tiers"].get("L3", {}).get("count") == 1


@pytest.mark.asyncio
async def test_stream_no_cache_header_bypasses_l0(app, monkeypatch):
    calls = 0

    async def fake_stream(request: InternalRequest):
        nonlocal calls
        calls += 1
        yield {"message": {"content": "fresh answer every time"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    body = {
        "model": "daari",
        "stream": True,
        "messages": [{"role": "user", "content": "no cache stream"}],
    }
    headers = {"X-Daari-No-Cache": "true"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/v1/chat/completions", json=body, headers=headers)
        await client.post("/v1/chat/completions", json=body, headers=headers)

    assert calls == 2


@pytest.mark.asyncio
async def test_agent_flow_stream_skips_l0(app, monkeypatch):
    """ADR-0004: agent turns skip L0 read and write."""
    calls = 0

    async def fake_stream(request: InternalRequest):
        nonlocal calls
        calls += 1
        yield {"message": {"content": "agent step"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)
    body = {
        "model": "daari",
        "stream": True,
        "messages": _agent_history_messages(),
        "tools": _demo_tools(),
    }

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/v1/chat/completions", json=body)
        await client.post("/v1/chat/completions", json=body)

    assert calls == 2


@pytest.mark.asyncio
async def test_report_endpoint_tracks_route_and_stream_usage(app, monkeypatch):
    """Issue #14: /v1/daari/report aggregates persisted usage with savings estimate."""

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="a response with enough characters to count",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
        )

    async def fake_stream(request: InternalRequest):
        yield {"message": {"content": "streamed answer body"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "usage ledger check"}]},
        )
        await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "usage ledger stream check"}],
            },
        )
        report = (await client.get("/v1/daari/report?days=7")).json()

    assert report["enabled"] is True
    assert report["totals"]["requests"] == 2
    assert report["totals"]["local_requests"] == 2
    assert report["totals"]["estimated_saved_usd"] > 0
    assert len(report["days"]) == 1
    assert report["days"][0]["tiers"]["L3"]["requests"] == 2


@pytest.mark.asyncio
async def test_tier_cap_header_caps_long_prompt_at_l3(app, monkeypatch):
    """Issue #3: X-Daari-Tier-Cap keeps long-context Ask requests on L3."""
    seen_tiers: list[str] = []

    def make_fake(tier: str):
        async def fake_execute(request: InternalRequest) -> InternalResponse:
            seen_tiers.append(tier)
            return InternalResponse(
                content="a confident answer that is long enough to avoid escalation",
                model=f"model-{tier.lower()}",
                daari_meta=DaariMeta(tier=tier, executor="ollama", provider_id="ollama", latency_ms=5),
            )

        return fake_execute

    router = app.state.ctx.router
    monkeypatch.setattr(router.ollama, "execute", make_fake("L3"))
    monkeypatch.setattr(router.ollama_l4, "execute", make_fake("L4"))
    monkeypatch.setattr(router.ollama_l5, "execute", make_fake("L5"))

    long_prompt = "please explain this " + "word " * 300

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": long_prompt}]},
            headers={**META_HEADERS, "X-Daari-Tier-Cap": "L3"},
        )

    assert response.status_code == 200
    assert response.json()["daari_meta"]["tier"] == "L3"
    assert seen_tiers == ["L3"]


@pytest.mark.asyncio
async def test_trace_recorded_and_retrievable_by_id(app, monkeypatch):
    """Issue #20: every request carries a trace_id whose steps are retrievable."""

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="a confident answer that is long enough",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=5),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={"model": "daari", "messages": [{"role": "user", "content": "what is a trace?"}]},
            headers=META_HEADERS,
        )
        trace_id = response.json()["daari_meta"]["trace_id"]
        detail = (await client.get(f"/v1/daari/traces/{trace_id}")).json()
        listing = (await client.get("/v1/daari/traces?limit=5")).json()

    assert trace_id
    steps = [s["step"] for s in detail["steps"]]
    assert "profile" in steps
    assert "l0_lookup" in steps
    assert "served" in steps
    assert detail["tier"] == "L3"
    assert any(item["trace_id"] == trace_id for item in listing["traces"])


@pytest.mark.asyncio
async def test_stream_requests_record_traces(app, monkeypatch):
    async def fake_stream(request: InternalRequest):
        yield {"message": {"content": "streamed trace answer"}}
        yield {"done": True}

    monkeypatch.setattr(app.state.ctx.router.ollama, "stream", fake_stream)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "stream": True,
                "messages": [{"role": "user", "content": "trace my stream"}],
            },
        )
        listing = (await client.get("/v1/daari/traces?limit=5")).json()

    assert listing["traces"], "stream request should have recorded a trace"
    detail_id = listing["traces"][0]["trace_id"]
    transport2 = ASGITransport(app=app)
    async with AsyncClient(transport=transport2, base_url="http://test") as client:
        detail = (await client.get(f"/v1/daari/traces/{detail_id}")).json()
    steps = [s["step"] for s in detail["steps"]]
    assert "served" in steps


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
    """With an explicit strip override, tool protocol is flattened to plain text.

    (Without the header this payload is an agent flow since issue #2 — see
    test_agent_flow_with_tool_history_passes_tools_through.)
    """
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
            headers={"X-Daari-Tools": "strip"},
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


def _anthropic_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[len("data: ") :]))
    return events


@pytest.mark.asyncio
async def test_anthropic_stream_reports_estimated_usage(app, monkeypatch):
    """Issue #5: usage must use the chars/4 estimate, not hardcoded zeros."""

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

    events = _anthropic_events(response.text)
    message_start = next(e for e in events if e.get("type") == "message_start")
    message_delta = next(e for e in events if e.get("type") == "message_delta")
    # "stream this" = 11 chars -> 2 input tokens; "Hello world" = 11 chars -> 2 output tokens
    assert message_start["message"]["usage"]["input_tokens"] == 2
    assert message_delta["usage"]["output_tokens"] == 2


@pytest.mark.asyncio
async def test_anthropic_stream_falls_back_l4_to_l3(app, monkeypatch):
    """Issue #5: Anthropic stream gets the same tier fallback as the OpenAI path."""

    async def broken_l4(_request: InternalRequest):
        raise RuntimeError("L4 model not pulled")
        yield  # pragma: no cover

    async def fake_l3(_request: InternalRequest):
        yield {"message": {"content": "fallback answer"}}
        yield {"done": True}

    router = app.state.ctx.router
    monkeypatch.setattr(router.ollama_l4, "stream", broken_l4)
    monkeypatch.setattr(router.ollama, "stream", fake_l3)

    long_prompt = "word " * 300  # >250 words -> L4 first

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            json={
                "model": "claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": long_prompt}],
                "stream": True,
            },
        )

    assert response.status_code == 200
    assert "fallback answer" in response.text
    events = _anthropic_events(response.text)
    deltas = [e for e in events if e.get("type") == "content_block_delta"]
    assert deltas and deltas[0]["daari_meta"]["tier"] == "L3"


@pytest.mark.asyncio
async def test_anthropic_stream_sanitizes_tool_history(app, monkeypatch):
    """Issue #5: tool-call history must be sanitized before hitting Ollama."""
    seen: dict = {}

    async def fake_stream(request: InternalRequest):
        seen["messages"] = [message.model_dump() for message in request.messages]
        yield {"message": {"content": "clean"}}
        yield {"done": True}

    router = app.state.ctx.router
    monkeypatch.setattr(router.ollama, "stream", fake_stream)

    request = InternalRequest(
        model="llama3.2:3b",
        messages=[
            Message(
                role="assistant",
                content=None,
                tool_calls=[{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}],
            ),
            Message(role="tool", content="result", tool_call_id="c1"),
            Message(role="user", content="continue please"),
        ],
    )
    chunks = [chunk async for chunk in router.stream_anthropic_events(request)]

    assert any("clean" in chunk for chunk in chunks)
    assert all(not message.get("tool_calls") for message in seen["messages"])
    assert all(message.get("role") != "tool" for message in seen["messages"])


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


@pytest.mark.asyncio
async def test_stream_serves_l1_hit_for_paraphrase(app, monkeypatch):
    """Issue #43: streaming requests get L1 semantic hits through the gateway."""
    from daari.cache.semantic import SemanticCache

    class KeywordEmbedder:
        async def embed(self, text: str) -> list[float] | None:
            if "capital of France" in text:
                return [1.0, 0.0]
            if "France's capital" in text:
                return [0.96, 0.28]  # cosine vs seed ≈ 0.96 — above hit threshold
            return [0.0, 1.0]

    router = app.state.ctx.router
    router.semantic_cache = SemanticCache(
        path=str(router.semantic_cache._path) + "-stream",
        embedder=KeywordEmbedder(),
        enabled=True,
        similarity_threshold=0.88,
    )
    await router.semantic_cache.put(
        InternalRequest(
            messages=[Message(role="user", content="What is the capital of France?")],
            model="daari",
        ),
        InternalResponse(
            content="Paris is the capital of France.",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=2),
        ),
    )

    async def fail_stream(request: InternalRequest):
        raise AssertionError("L1 hit should never reach the model")
        yield

    monkeypatch.setattr(router.ollama, "stream", fail_stream)

    payload = {
        "model": "daari",
        "stream": True,
        "messages": [{"role": "user", "content": "Tell me France's capital"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=payload)

    assert response.status_code == 200
    assert "Paris is the capital of France." in response.text
    assert "data: [DONE]" in response.text


@pytest.mark.asyncio
async def test_feedback_endpoint_joins_by_trace_id(app, monkeypatch):
    """Issue #53: explicit accept/reject feedback lands on the recorded outcome."""

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content=MOCK_MODEL_CONTENT,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama", latency_ms=3),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    payload = {
        "model": "llama3.2:3b",
        "messages": [{"role": "user", "content": "rate this answer"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/v1/chat/completions", json=payload, headers=META_HEADERS)
        trace_id = first.json()["daari_meta"]["trace_id"]
        assert trace_id

        ok = await client.post(
            "/v1/daari/feedback", json={"trace_id": trace_id, "signal": "accept"}
        )
        unknown = await client.post(
            "/v1/daari/feedback", json={"trace_id": "does-not-exist", "signal": "accept"}
        )
        invalid = await client.post(
            "/v1/daari/feedback", json={"trace_id": trace_id, "signal": "maybe"}
        )

    assert ok.status_code == 200
    assert ok.json()["recorded"] is True
    assert unknown.status_code == 404
    assert invalid.status_code == 422

    rows = app.state.ctx.router.feedback_store.outcomes(limit=5)
    assert rows[0]["trace_id"] == trace_id
    assert rows[0]["signal"] == "accept"

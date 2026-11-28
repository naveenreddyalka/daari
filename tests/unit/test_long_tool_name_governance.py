"""Fence: tool-name matching never truncates at 64 chars (#2369).

LiteLLM 1.108.12 LTS fixed a fail-open where tool_policy / guardrails
truncated at Anthropic's 64-char tool-name limit (#47434 / #52717). daari
matches full names via fnmatch / set membership — these hermetic tests
are the immunity proof.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest, Message
from daari.gateway.mcp_policy import McpServerToolSubset, McpToolPolicy, TOOL_DENIED
from daari.gateway.sampling import (
    SamplingParams,
    filter_tools_by_allowed,
    parse_allowed_tools_choice,
)
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS, mock_all_ollama_executors

# Longer than Anthropic's historical 64-char tool-name ceiling.
LONG = "x" * 70
LONG_BLOCKED = f"blocked_{LONG}"
LONG_GRANTED = f"granted_{LONG}"
assert len(LONG_BLOCKED) > 64
assert len(LONG_GRANTED) > 64


def _fn_tool(name: str) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "parameters": {"type": "object", "properties": {}}},
    }


def test_mcp_policy_deny_matches_full_long_name():
    policy = McpToolPolicy(deny=(LONG_BLOCKED,))
    assert not policy.allows(LONG_BLOCKED)
    # Truncating to 64 would miss the deny suffix — prove we did not.
    assert policy.allows(LONG_BLOCKED[:64])


def test_mcp_policy_allow_requires_full_long_name():
    policy = McpToolPolicy(allow=(LONG_GRANTED,))
    assert policy.allows(LONG_GRANTED)
    assert not policy.allows(LONG_GRANTED[:64])


def test_mcp_server_tool_subset_long_name():
    subset = McpServerToolSubset(by_server={"demo": (LONG_GRANTED,)})
    assert subset.allows("demo", LONG_GRANTED)
    assert not subset.allows("demo", LONG_GRANTED[:64])
    deny = McpServerToolSubset(by_server={"demo": ()})
    assert not deny.allows("demo", LONG_BLOCKED)


def test_chat_allowed_tools_filters_long_names():
    """chat/completions tool_choice.allowed_tools governance (#2251 / #2369)."""
    tools = [_fn_tool(LONG_BLOCKED), _fn_tool(LONG_GRANTED), _fn_tool("short")]
    choice = {
        "type": "allowed_tools",
        "allowed_tools": {
            "mode": "auto",
            "tools": [{"type": "function", "function": {"name": LONG_GRANTED}}],
        },
    }
    filtered = filter_tools_by_allowed(tools, choice)
    assert [t["function"]["name"] for t in filtered] == [LONG_GRANTED]
    parsed = parse_allowed_tools_choice(choice)
    assert parsed is not None
    assert LONG_GRANTED in parsed[1]
    assert LONG_GRANTED[:64] not in parsed[1]


def test_messages_facade_preserves_and_filters_long_tool_names():
    """/v1/messages Anthropic bridge keeps full names; allowed_tools filters."""
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude-sonnet-5",
        temperature=0.0,
        tools=[_fn_tool(LONG_BLOCKED), _fn_tool(LONG_GRANTED)],
        sampling=SamplingParams(
            tool_choice={
                "type": "allowed_tools",
                "mode": "required",
                "tools": [{"type": "function", "function": {"name": LONG_GRANTED}}],
            }
        ),
    )
    payload = to_anthropic_payload(request, model="claude-sonnet-5", stream=False)
    names = [t["name"] for t in payload["tools"]]
    assert names == [LONG_GRANTED]
    assert all(len(n) > 64 for n in names)


@pytest.mark.asyncio
async def test_mcp_ingress_denies_long_blocked_tool(settings, monkeypatch):
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse

    settings.integrations.mcp_policy.deny = [LONG_BLOCKED]
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_execute(_request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="should not run",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": LONG_BLOCKED, "arguments": {}},
            },
            headers=META_HEADERS,
        )
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            headers=META_HEADERS,
        )
    assert denied.json()["error"]["code"] == TOOL_DENIED
    listed_names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert LONG_BLOCKED not in listed_names


@pytest.mark.asyncio
async def test_mcp_egress_server_tools_deny_long_name(settings, monkeypatch):
    """Egress relay honors server_tools allowlist for >64-char upstream tools."""
    import json
    import socket

    import httpx

    from daari.config.settings import McpServerSettings
    from daari.gateway.responses_mcp import function_name_for

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port or 0))]

    monkeypatch.setattr("daari.security.egress_url.socket.getaddrinfo", fake_getaddrinfo)

    settings.integrations.mcp_aggregate_egress.enabled = True
    settings.integrations.mcp_servers = [
        McpServerSettings(id="demo", url="http://mcp.test/rpc"),
    ]
    settings.integrations.mcp_policy.server_tools = {"demo": [LONG_GRANTED]}

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        if body.get("method") == "tools/list":
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": body.get("id", 1),
                    "result": {
                        "tools": [
                            {
                                "name": LONG_GRANTED,
                                "description": "ok",
                                "inputSchema": {"type": "object"},
                            },
                            {
                                "name": LONG_BLOCKED,
                                "description": "blocked",
                                "inputSchema": {"type": "object"},
                            },
                        ]
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body.get("id", 1),
                "result": {"content": [{"type": "text", "text": "ok"}]},
            },
        )

    class Patched(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", Patched)
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    granted = function_name_for("demo", LONG_GRANTED)
    blocked = function_name_for("demo", LONG_BLOCKED)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        listed = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers=META_HEADERS,
        )
        denied = await client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": blocked, "arguments": {}},
            },
            headers=META_HEADERS,
        )
    names = {t["name"] for t in listed.json()["result"]["tools"]}
    assert granted in names
    assert blocked not in names
    assert denied.json()["error"]["code"] == TOOL_DENIED


@pytest.mark.asyncio
async def test_granted_long_tool_name_round_trips_local_tier(settings, monkeypatch):
    """Granted >64-char tool name survives tools[] out and tool_calls back."""
    from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse

    captured: dict = {}

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        captured["tools"] = [t.get("function", {}).get("name") for t in (request.tools or [])]
        return InternalResponse(
            content="",
            model=request.model or "llama3.2:3b",
            finish_reason="tool_calls",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": LONG_GRANTED, "arguments": "{}"},
                }
            ],
            daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama:l3"),
        )

    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    mock_all_ollama_executors(monkeypatch, app.state.ctx.router, fake_execute)
    headers = {**META_HEADERS, "X-Daari-Tools": "passthrough"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/chat/completions",
            json={
                "model": "daari",
                "messages": [{"role": "user", "content": "use the tool"}],
                "tools": [_fn_tool(LONG_GRANTED)],
                "tool_choice": {
                    "type": "allowed_tools",
                    "mode": "required",
                    "tools": [{"type": "function", "function": {"name": LONG_GRANTED}}],
                },
            },
            headers=headers,
        )
    assert response.status_code == 200
    assert captured.get("tools") == [LONG_GRANTED]
    call = response.json()["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == LONG_GRANTED

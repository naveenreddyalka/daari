"""Anthropic tool passthrough for Claude Code agent flows (issue #84)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.anthropic import (
    AnthropicMessageIn,
    anthropic_message_to_internal,
    anthropic_tools_to_openai,
)
from daari.gateway.internal import InternalRequest
from daari.router.router import AppContext
from daari.server.app import create_app

TOOLS = [
    {
        "name": "read_file",
        "description": "Read a file from disk",
        "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
    }
]


@pytest.fixture
def app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data:"):
            events.append(json.loads(line[len("data:") :].strip()))
    return events


class TestConversion:
    def test_tools_convert_to_openai_shape(self):
        converted = anthropic_tools_to_openai(TOOLS)
        assert converted == [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file from disk",
                    "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
                },
            }
        ]

    def test_tools_without_name_skipped(self):
        assert anthropic_tools_to_openai([{"description": "nameless"}]) == []

    def test_tool_use_blocks_become_tool_calls(self):
        message = AnthropicMessageIn(
            role="assistant",
            content=[
                {"type": "text", "text": "let me check"},
                {"type": "tool_use", "id": "toolu_1", "name": "read_file", "input": {"path": "a.py"}},
            ],
        )
        expanded = anthropic_message_to_internal(message)
        assert len(expanded) == 1
        assert expanded[0].content == "let me check"
        call = expanded[0].tool_calls[0]
        assert call["id"] == "toolu_1"
        assert call["function"]["name"] == "read_file"
        assert json.loads(call["function"]["arguments"]) == {"path": "a.py"}

    def test_tool_result_blocks_become_tool_messages(self):
        message = AnthropicMessageIn(
            role="user",
            content=[
                {"type": "tool_result", "tool_use_id": "toolu_1", "content": "file contents here"},
            ],
        )
        expanded = anthropic_message_to_internal(message)
        assert len(expanded) == 1
        assert expanded[0].role == "tool"
        assert expanded[0].content == "file contents here"

    def test_plain_string_message_unchanged(self):
        message = AnthropicMessageIn(role="user", content="just chatting")
        expanded = anthropic_message_to_internal(message)
        assert len(expanded) == 1
        assert expanded[0].role == "user"
        assert expanded[0].content == "just chatting"


@pytest.mark.asyncio
async def test_stream_with_tools_emits_tool_use_blocks(app, monkeypatch):
    """A Claude Code agent turn gets tool_use content blocks + stop_reason tool_use."""
    seen: dict = {}

    async def fake_stream(request: InternalRequest):
        seen["tools"] = request.tools
        yield {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "read_file", "arguments": {"path": "main.py"}}}
                ],
            },
            "done": False,
        }
        yield {"message": {"role": "assistant", "content": ""}, "done": True}

    router = app.state.ctx.router
    monkeypatch.setattr(router.ollama, "stream", fake_stream)

    payload = {
        "model": "daari",
        "max_tokens": 512,
        "stream": True,
        "tools": TOOLS,
        "messages": [{"role": "user", "content": "read main.py for me"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/messages", json=payload)

    assert response.status_code == 200
    # Tools were forwarded to the executor in OpenAI shape.
    assert seen["tools"][0]["function"]["name"] == "read_file"

    events = _events(response.text)
    starts = [e for e in events if e.get("type") == "content_block_start"]
    tool_starts = [e for e in starts if e["content_block"]["type"] == "tool_use"]
    assert tool_starts, "expected a tool_use content block"
    assert tool_starts[0]["content_block"]["name"] == "read_file"

    json_deltas = [
        e
        for e in events
        if e.get("type") == "content_block_delta"
        and e["delta"]["type"] == "input_json_delta"
    ]
    assert json.loads(json_deltas[0]["delta"]["partial_json"]) == {"path": "main.py"}

    message_deltas = [e for e in events if e.get("type") == "message_delta"]
    assert message_deltas[-1]["delta"]["stop_reason"] == "tool_use"


@pytest.mark.asyncio
async def test_stream_tool_result_round_trip(app, monkeypatch):
    """Multi-turn: tool_use + tool_result history reaches Ollama as tool messages."""
    seen: dict = {}

    async def fake_stream(request: InternalRequest):
        seen["messages"] = [message.model_dump() for message in request.messages]
        seen["tools"] = request.tools
        yield {"message": {"role": "assistant", "content": "The file defines main()."}, "done": False}
        yield {"message": {"role": "assistant", "content": ""}, "done": True}

    router = app.state.ctx.router
    monkeypatch.setattr(router.ollama, "stream", fake_stream)

    payload = {
        "model": "daari",
        "max_tokens": 512,
        "stream": True,
        "tools": TOOLS,
        "messages": [
            {"role": "user", "content": "read main.py for me"},
            {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_9", "name": "read_file", "input": {"path": "main.py"}}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_9", "content": "def main(): ..."}
                ],
            },
        ],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/messages", json=payload)

    assert response.status_code == 200
    assert "The file defines main()." in response.text
    roles = [message["role"] for message in seen["messages"]]
    assert "tool" in roles
    assert any(message.get("tool_calls") for message in seen["messages"])
    events = _events(response.text)
    message_deltas = [e for e in events if e.get("type") == "message_delta"]
    assert message_deltas[-1]["delta"]["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_strip_header_forces_plain_chat(app, monkeypatch):
    """X-Daari-Tools: strip disables passthrough for parity with the OpenAI gateway."""
    seen: dict = {}

    async def fake_stream(request: InternalRequest):
        seen["tools"] = request.tools
        yield {"message": {"role": "assistant", "content": "no tools used"}, "done": True}

    router = app.state.ctx.router
    monkeypatch.setattr(router.ollama, "stream", fake_stream)

    payload = {
        "model": "daari",
        "max_tokens": 512,
        "stream": True,
        "tools": TOOLS,
        "messages": [{"role": "user", "content": "hello with tools attached"}],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages", json=payload, headers={"X-Daari-Tools": "strip"}
        )

    assert response.status_code == 200
    assert seen["tools"] is None


class TestHoistSystemMessages:
    """Claude Code trailing system messages (issue #94)."""

    def test_trailing_system_hoisted(self):
        from daari.gateway.anthropic import hoist_system_messages
        from daari.gateway.internal import Message

        messages = [
            Message(role="system", content="base system"),
            Message(role="user", content="question"),
            Message(role="system", content="SessionStart hook context"),
        ]
        hoisted = hoist_system_messages(messages)
        assert [m.role for m in hoisted] == ["system", "system", "user"]
        assert hoisted[0].content == "base system"
        assert hoisted[1].content == "SessionStart hook context"
        assert hoisted[-1].content == "question"

    def test_leading_systems_untouched(self):
        from daari.gateway.anthropic import hoist_system_messages
        from daari.gateway.internal import Message

        messages = [
            Message(role="system", content="s1"),
            Message(role="user", content="u1"),
            Message(role="assistant", content="a1"),
            Message(role="user", content="u2"),
        ]
        assert hoist_system_messages(messages) is messages

    def test_no_system_messages_noop(self):
        from daari.gateway.anthropic import hoist_system_messages
        from daari.gateway.internal import Message

        messages = [Message(role="user", content="u1")]
        assert hoist_system_messages(messages) is messages


@pytest.mark.asyncio
async def test_claude_code_trailing_system_reordered_before_ollama(app, monkeypatch):
    """The captured claude-cli 2.1.215 shape: messages=[user, system] plus a
    top-level system field. Ollama must receive all system messages first."""
    seen: dict = {}

    async def fake_stream(request: InternalRequest):
        seen["roles"] = [m.role for m in request.messages]
        seen["last"] = request.messages[-1].content
        yield {"message": {"role": "assistant", "content": "Paris."}, "done": False}
        yield {"message": {"role": "assistant", "content": ""}, "done": True}

    router = app.state.ctx.router
    for attr in ("ollama", "ollama_l3", "ollama_l4", "ollama_l5"):
        executor = getattr(router, attr, None)
        if executor is not None:
            monkeypatch.setattr(executor, "stream", fake_stream)

    payload = {
        "model": "daari",
        "max_tokens": 512,
        "stream": True,
        "tools": TOOLS,
        "system": [{"type": "text", "text": "You are Claude Code."}],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "<system-reminder>claudeMd context</system-reminder>"},
                    {"type": "text", "text": "what is the capital of France?"},
                ],
            },
            {"role": "system", "content": "SessionStart hook additional context: superpowers"},
        ],
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/messages", json=payload)

    assert response.status_code == 200
    assert "Paris." in response.text
    assert seen["roles"] == ["system", "system", "user"], (
        "system messages must be hoisted ahead of the user turn"
    )
    assert "capital of France" in seen["last"]

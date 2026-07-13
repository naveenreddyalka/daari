"""Ollama executor payload/diagnostics hardening (issue #88)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.gateway.internal import InternalRequest, Message
from daari.router.router import OllamaExecutor, OllamaRequestError, estimate_num_ctx


class TestEstimateNumCtx:
    def test_small_prompt_gets_floor(self):
        assert estimate_num_ctx(1000) == 4096

    def test_large_prompt_scales_up(self):
        # 80k chars ≈ 20k tokens + 2048 headroom → 32768.
        assert estimate_num_ctx(80_000) == 32768

    def test_medium_prompt_doubles(self):
        # 24k chars ≈ 6k tokens + headroom → 8192.
        assert estimate_num_ctx(24_000) == 8192

    def test_ceiling_clamped(self):
        assert estimate_num_ctx(10_000_000) == 32768


class TestPayload:
    def _executor(self) -> OllamaExecutor:
        return OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")

    def test_string_tool_arguments_converted_to_object(self):
        request = InternalRequest(
            model="llama3.2:3b",
            messages=[
                Message(role="user", content="read it"),
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        {
                            "id": "t1",
                            "type": "function",
                            "function": {"name": "read_file", "arguments": '{"path": "a.py"}'},
                        }
                    ],
                ),
                Message(role="tool", content="contents"),
            ],
        )
        payload = self._executor()._payload(request, "llama3.2:3b", stream=True)
        args = payload["messages"][1]["tool_calls"][0]["function"]["arguments"]
        assert args == {"path": "a.py"}

    def test_invalid_arguments_string_becomes_empty_object(self):
        request = InternalRequest(
            model="llama3.2:3b",
            messages=[
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=[
                        {"id": "t1", "type": "function", "function": {"name": "f", "arguments": "{broken"}}
                    ],
                ),
                Message(role="user", content="hi"),
            ],
        )
        payload = self._executor()._payload(request, "llama3.2:3b", stream=False)
        assert payload["messages"][0]["tool_calls"][0]["function"]["arguments"] == {}

    def test_contentless_messages_dropped(self):
        request = InternalRequest(
            model="llama3.2:3b",
            messages=[
                Message(role="assistant", content=None),
                Message(role="user", content="hello"),
            ],
        )
        payload = self._executor()._payload(request, "llama3.2:3b", stream=False)
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

    def test_num_ctx_always_present(self):
        request = InternalRequest(
            model="llama3.2:3b", messages=[Message(role="user", content="hi")]
        )
        payload = self._executor()._payload(request, "llama3.2:3b", stream=False)
        assert payload["options"]["num_ctx"] == 4096

    def test_num_ctx_accounts_for_tools(self):
        request = InternalRequest(
            model="llama3.2:3b",
            messages=[Message(role="user", content="x" * 20_000)],
            tools=[{"type": "function", "function": {"name": "t", "parameters": {"pad": "y" * 20_000}}}],
        )
        payload = self._executor()._payload(request, "llama3.2:3b", stream=False)
        assert payload["options"]["num_ctx"] >= 8192


@pytest.mark.asyncio
async def test_execute_error_includes_ollama_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid tool call arguments"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", patched_client)
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    request = InternalRequest(model="llama3.2:3b", messages=[Message(role="user", content="hi")])

    with pytest.raises(OllamaRequestError) as excinfo:
        await executor.execute(request)
    assert excinfo.value.status_code == 400
    assert "invalid tool call arguments" in str(excinfo.value)


@pytest.mark.asyncio
async def test_stream_error_includes_ollama_body(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "messages must not be empty"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", patched_client)
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    request = InternalRequest(model="llama3.2:3b", messages=[Message(role="user", content="hi")])

    with pytest.raises(OllamaRequestError) as excinfo:
        async for _ in executor.stream(request):
            pass
    assert "messages must not be empty" in str(excinfo.value)


@pytest.mark.asyncio
async def test_execute_success_unaffected(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["options"]["num_ctx"] >= 4096
        return httpx.Response(
            200, json={"message": {"role": "assistant", "content": "fine"}, "done": True}
        )

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("daari.router.router.httpx.AsyncClient", patched_client)
    executor = OllamaExecutor(base_url="http://test", default_model="llama3.2:3b")
    request = InternalRequest(model="llama3.2:3b", messages=[Message(role="user", content="hi")])

    response = await executor.execute(request)
    assert response.content == "fine"
    assert response.daari_meta.tier == "L3"

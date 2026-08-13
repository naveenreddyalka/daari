"""Native Anthropic /v1/messages egress (issue #166).

`provider: anthropic` used to POST an OpenAI body at /chat/completions and
sprinkle cache_control on system strings. That is not the Anthropic API.
"""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import InternalRequest, Message
from daari.router.anthropic_messages import infer_frontier_kind, to_anthropic_payload
from daari.router.frontier import FrontierExecutor
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.conftest import META_HEADERS


def _request(**kwargs) -> InternalRequest:
    messages = kwargs.pop("messages", [Message(role="user", content="hello")])
    return InternalRequest(messages=messages, model="daari", **kwargs)


class TestPayload:
    def test_system_messages_become_the_system_field(self):
        payload = to_anthropic_payload(
            _request(
                messages=[
                    Message(role="system", content="you are terse"),
                    Message(role="user", content="hi"),
                ]
            ),
            model="claude-sonnet-4-0",
        )
        assert payload["system"]
        assert payload["messages"][0]["role"] == "user"
        assert all(m["role"] != "system" for m in payload["messages"])

    def test_cache_control_marks_the_system_prefix(self):
        payload = to_anthropic_payload(
            _request(
                messages=[
                    Message(role="system", content="stable"),
                    Message(role="user", content="q"),
                ]
            ),
            model="claude-sonnet-4-0",
            prompt_cache=True,
        )
        system = payload["system"]
        assert isinstance(system, list)
        assert system[-1]["cache_control"] == {"type": "ephemeral"}

    def test_tool_calls_become_tool_use_blocks(self):
        payload = to_anthropic_payload(
            _request(
                messages=[
                    Message(role="user", content="search it"),
                    Message(
                        role="assistant",
                        content="",
                        tool_calls=[
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "search",
                                    "arguments": '{"q": "x"}',
                                },
                            }
                        ],
                    ),
                    Message(role="tool", content="found 3"),
                ]
            ),
            model="claude-sonnet-4-0",
        )
        assistant = payload["messages"][1]
        assert assistant["content"][0]["type"] == "tool_use"
        assert assistant["content"][0]["name"] == "search"
        user_result = payload["messages"][2]
        assert user_result["content"][0]["type"] == "tool_result"

    def test_openai_tools_are_translated(self):
        payload = to_anthropic_payload(
            _request(
                tools=[
                    {
                        "type": "function",
                        "function": {
                            "name": "search",
                            "description": "find things",
                            "parameters": {"type": "object"},
                        },
                    }
                ]
            ),
            model="claude-sonnet-4-0",
        )
        assert payload["tools"][0]["name"] == "search"
        assert payload["tools"][0]["input_schema"] == {"type": "object"}

    def test_max_tokens_is_always_present(self):
        """Anthropic requires it; OpenAI clients often omit it."""
        payload = to_anthropic_payload(_request(), model="claude-sonnet-4-0")
        assert payload["max_tokens"] >= 1


class TestKind:
    def test_id_anthropic_is_anthropic(self):
        assert infer_frontier_kind("anthropic", "https://api.openai.com/v1") == "anthropic"

    def test_anthropic_host_is_anthropic_even_with_another_id(self):
        assert infer_frontier_kind("primary", "https://api.anthropic.com") == "anthropic"

    def test_openai_stays_openai(self):
        assert infer_frontier_kind("openai", "https://api.openai.com/v1") == "openai"


class TestExecutor:
    @pytest.mark.asyncio
    async def test_anthropic_provider_posts_messages_not_chat_completions(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["headers"] = dict(request.headers)
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "bonjour"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 11, "output_tokens": 3},
                },
            )

        executor = FrontierExecutor(
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-0",
            api_key="sk-ant-test",
            provider="anthropic",
            transport=httpx.MockTransport(handler),
        )
        response = await executor.execute(
            _request(), escalated_from="L3", local_confidence=0.2
        )

        assert "/v1/messages" in seen["url"]
        assert "/chat/completions" not in seen["url"]
        assert seen["headers"].get("x-api-key") == "sk-ant-test"
        assert seen["headers"].get("anthropic-version")
        assert response.content == "bonjour"
        assert response.daari_meta.input_tokens == 11
        assert response.daari_meta.output_tokens == 3
        assert response.daari_meta.usage_estimated is False

    @pytest.mark.asyncio
    async def test_openai_provider_is_unchanged(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                },
            )

        executor = FrontierExecutor(
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o",
            api_key="sk-test",
            provider="openai",
            transport=httpx.MockTransport(handler),
        )
        await executor.execute(_request(), escalated_from="L3", local_confidence=0.2)
        assert "/chat/completions" in seen["url"]
        assert seen["auth"] == "Bearer sk-test"

    @pytest.mark.asyncio
    async def test_anthropic_stream_yields_text_deltas(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = (
                b"event: content_block_delta\n"
                b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hel"}}\n\n'
                b"event: content_block_delta\n"
                b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"lo"}}\n\n'
                b"event: message_stop\n"
                b'data: {"type":"message_stop"}\n\n'
            )
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=body,
            )

        executor = FrontierExecutor(
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-0",
            api_key="sk-ant-test",
            provider="anthropic",
            transport=httpx.MockTransport(handler),
        )
        deltas = [
            delta
            async for delta in executor.stream(
                _request(), escalated_from="L3", local_confidence=0.2
            )
        ]
        assert "".join(deltas) == "Hello"


class TestCountTokens:
    @pytest.mark.asyncio
    async def test_count_tokens_returns_an_input_count(self, settings):
        app = create_app(settings)
        app.state.ctx = AppContext.from_settings(settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/messages/count_tokens",
                json={
                    "model": "daari",
                    "messages": [{"role": "user", "content": "hello there friend"}],
                },
                headers=META_HEADERS,
            )
        assert response.status_code == 200, response.text
        assert response.json()["input_tokens"] > 0

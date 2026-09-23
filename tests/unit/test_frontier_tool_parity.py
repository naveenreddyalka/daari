"""Frontier tool_choice / output_format / streamed tool-call parity (#934)."""

from __future__ import annotations

import json

import httpx
import pytest

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import (
    openai_tool_choice_to_anthropic,
    to_anthropic_payload,
)
from daari.router.frontier import FrontierExecutor
from daari.router.router import Router


def _request(**sampling_kwargs) -> InternalRequest:
    sampling = SamplingParams(**sampling_kwargs) if sampling_kwargs else SamplingParams()
    return InternalRequest(
        messages=[Message(role="user", content="call a tool")],
        model="daari",
        temperature=0.0,
        sampling=sampling,
        tools=[{"type": "function", "function": {"name": "lookup", "parameters": {}}}],
    )


def test_openai_tool_choice_maps_to_anthropic():
    assert openai_tool_choice_to_anthropic("auto") == {"type": "auto"}
    assert openai_tool_choice_to_anthropic("none") == {"type": "none"}
    assert openai_tool_choice_to_anthropic("required") == {"type": "any"}
    assert openai_tool_choice_to_anthropic(
        {"type": "function", "function": {"name": "lookup"}}
    ) == {"type": "tool", "name": "lookup"}


def test_to_anthropic_payload_forwards_tool_choice_and_output_format():
    request = _request(
        tool_choice="required",
        json_schema={"type": "object", "properties": {"x": {"type": "string"}}},
    )
    payload = to_anthropic_payload(request, model="claude", stream=False)
    assert payload["tool_choice"] == {"type": "any"}
    assert payload["output_format"] == {
        "type": "json_schema",
        "schema": {"type": "object", "properties": {"x": {"type": "string"}}},
    }


def test_openai_payload_includes_tool_choice():
    params = SamplingParams(tool_choice={"type": "function", "function": {"name": "f"}})
    assert params.openai_payload()["tool_choice"]["function"]["name"] == "f"


def test_openai_stream_and_nonstream_payloads_share_tools_and_tool_choice():
    """Non-stream L6 OpenAI must carry tools/tool_choice like the stream path (#1006)."""
    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
    )
    request = _request(tool_choice="required")
    stream_payload = executor._openai_payload(request, stream=True)
    nonstream_payload = executor._openai_payload(request, stream=False)
    assert nonstream_payload.get("tools") == request.tools
    assert nonstream_payload.get("tool_choice") == "required"
    assert nonstream_payload["tools"] == stream_payload["tools"]
    assert nonstream_payload["tool_choice"] == stream_payload["tool_choice"]
    assert stream_payload["stream"] is True
    assert nonstream_payload["stream"] is False


@pytest.mark.asyncio
async def test_frontier_execute_sends_tools_on_openai():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        captured.append(payload)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "lookup", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    response = await executor.execute(
        _request(tool_choice="required"), escalated_from="L3", local_confidence=0.1
    )
    assert captured[0]["stream"] is False
    assert captured[0]["tools"] == _request().tools
    assert captured[0]["tool_choice"] == "required"
    assert response.tool_calls is not None
    assert response.tool_calls[0]["function"]["name"] == "lookup"


@pytest.mark.asyncio
async def test_frontier_stream_forwards_openai_tool_call_deltas():
    body = (
        'data: {"choices":[{"delta":{"role":"assistant"}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1",'
        '"type":"function","function":{"name":"lookup","arguments":"{\\"q\\":"}}]}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
        '"function":{"arguments":"\\"x\\"}"}}]}}]}\n\n'
        "data: [DONE]\n\n"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert "tools" in payload
        assert payload.get("tool_choice") == "required"
        return httpx.Response(
            200, content=body.encode(), headers={"content-type": "text/event-stream"}
        )

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o",
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
    )
    events = [
        e
        async for e in executor.stream(
            _request(tool_choice="required"), escalated_from="L3", local_confidence=0.1
        )
    ]
    tool_chunks = [e for e in events if isinstance(e, dict) and e.get("tool_calls")]
    assert len(tool_chunks) == 2
    assert tool_chunks[0]["tool_calls"][0]["function"]["name"] == "lookup"


@pytest.mark.asyncio
async def test_frontier_stream_forwards_anthropic_tool_blocks():
    body = (
        b"event: content_block_start\n"
        b'data: {"type":"content_block_start","index":0,'
        b'"content_block":{"type":"tool_use","id":"toolu_1","name":"lookup","input":{}}}\n\n'
        b"event: content_block_delta\n"
        b'data: {"type":"content_block_delta","index":0,'
        b'"delta":{"type":"input_json_delta","partial_json":"{\\"q\\":\\"x\\"}"}}\n\n'
        b"event: content_block_stop\n"
        b'data: {"type":"content_block_stop","index":0}\n\n'
        b"event: message_stop\n"
        b'data: {"type":"message_stop"}\n\n'
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tool_choice"] == {"type": "any"}
        assert payload["output_format"]["type"] == "json_schema"
        return httpx.Response(200, content=body, headers={"content-type": "text/event-stream"})

    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-sonnet-4-0",
        api_key="sk-ant-test",
        provider="anthropic",
        transport=httpx.MockTransport(handler),
    )
    request = _request(
        tool_choice="required",
        json_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )
    events = [e async for e in executor.stream(request, escalated_from="L3", local_confidence=0.1)]
    anthropic_events = [e["anthropic_event"] for e in events if isinstance(e, dict) and "anthropic_event" in e]
    assert any(e.get("type") == "content_block_start" for e in anthropic_events)
    assert any(
        (e.get("delta") or {}).get("type") == "input_json_delta" for e in anthropic_events
    )


class _ToolFrontier:
    api_key = "sk-test"

    def __init__(self) -> None:
        self.stream_calls = 0

    async def execute(self, request, escalated_from=None, local_confidence=None):
        raise AssertionError("relay must use stream, not execute")

    async def stream(self, request, escalated_from=None, local_confidence=None):
        self.stream_calls += 1
        yield {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": '{"q":"x"}'},
                }
            ]
        }


@pytest.mark.asyncio
async def test_openai_gateway_relays_frontier_tool_calls(tmp_path):
    from daari.cache.exact import ExactCache
    from daari.cache.semantic import SemanticCache
    from daari.observability.metrics import Metrics
    from daari.router.router import OllamaExecutor
    from tests.conftest import NoopEmbedder

    class _LocalIdk(OllamaExecutor):
        def __init__(self) -> None:
            super().__init__(base_url="http://test", default_model="llama3.2:3b")

        async def stream(self, request, **kwargs):  # type: ignore[override]
            yield {"message": {"role": "assistant", "content": "idk"}, "done": True}

        async def execute(self, request, model=None, **kwargs):  # type: ignore[override]
            return InternalResponse(
                content="idk",
                model=self.default_model,
                daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
            )

    frontier = _ToolFrontier()
    local = _LocalIdk()
    router = Router(
        cache=ExactCache(str(tmp_path / "l0"), enabled=False),
        semantic_cache=SemanticCache(str(tmp_path / "l1"), NoopEmbedder(), enabled=False),
        ollama=local,
        ollama_l3=local,
        ollama_l4=local,
        ollama_l5=local,
        frontier=frontier,
        metrics=Metrics(),
        frontier_enabled=True,
        confidence_threshold=0.99,
    )
    request = _request()
    chunks: list[str] = []
    async for chunk in router.stream_openai_chunks(request):
        chunks.append(chunk)
    body = "".join(chunks)
    assert frontier.stream_calls == 1
    assert "tool_calls" in body
    assert "lookup" in body
    assert "call_abc" in body

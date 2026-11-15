"""Round-trip OpenAI encrypted reasoning on /v1/messages (#2214)."""

from __future__ import annotations

import json

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.anthropic import AnthropicMessageIn, anthropic_message_to_internal
from daari.gateway.content import sanitize_messages_for_ollama
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.frontier import FrontierExecutor
from daari.router.openai_encrypted_reasoning import (
    DAARI_ENCRYPTED_REASONING_PREFIX,
    is_openai_encrypted_reasoning_block,
    pack_encrypted_reasoning_block,
    strip_openai_encrypted_reasoning,
    unpack_encrypted_reasoning,
)
from daari.router.retry import RetryPolicy
from daari.router.router import AppContext
from daari.server.app import create_app


def test_pack_unpack_encrypted_reasoning_round_trip():
    block = pack_encrypted_reasoning_block("enc-blob-1")
    assert block["type"] == "redacted_thinking"
    assert block["data"].startswith(DAARI_ENCRYPTED_REASONING_PREFIX)
    assert unpack_encrypted_reasoning(block) == "enc-blob-1"
    assert is_openai_encrypted_reasoning_block(block)
    assert not is_openai_encrypted_reasoning_block(
        {"type": "redacted_thinking", "data": "anthropic-native-blob"}
    )


def test_anthropic_message_to_internal_keeps_packed_block():
    packed = pack_encrypted_reasoning_block("enc-keep")
    messages = anthropic_message_to_internal(
        AnthropicMessageIn(
            role="assistant",
            content=[packed, {"type": "text", "text": "done"}],
        )
    )
    assert len(messages) == 1
    assert messages[0].thinking_blocks
    assert unpack_encrypted_reasoning(messages[0].thinking_blocks[0]) == "enc-keep"


def test_to_anthropic_payload_drops_openai_encrypted_blocks():
    """OpenAI-opaque payloads must not reach Anthropic executors (#2214)."""
    packed = pack_encrypted_reasoning_block("openai-only")
    native = {"type": "thinking", "thinking": "plan", "signature": "sig"}
    request = InternalRequest(
        messages=[
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content="ok",
                thinking_blocks=[packed, native],
            ),
        ],
        model="daari",
    )
    payload = to_anthropic_payload(request, model="claude-sonnet-4-0")
    types = [b["type"] for b in payload["messages"][1]["content"]]
    assert "redacted_thinking" not in types
    assert types[0] == "thinking"
    assert types[1] == "text"


def test_sanitize_strips_openai_encrypted_blocks():
    packed = pack_encrypted_reasoning_block("local-drop")
    sanitized = sanitize_messages_for_ollama(
        [
            Message(
                role="assistant",
                content="answer",
                thinking_blocks=[packed],
            )
        ]
    )
    assert sanitized[0].thinking_blocks == []


def test_strip_helper_preserves_anthropic_native():
    packed = pack_encrypted_reasoning_block("x")
    native = {"type": "redacted_thinking", "data": "anthropic-blob"}
    msg = Message(role="assistant", content="a", thinking_blocks=[packed, native])
    strip_openai_encrypted_reasoning([msg])
    assert msg.thinking_blocks == [native]


@pytest.mark.asyncio
async def test_openai_frontier_requests_and_returns_encrypted_reasoning():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        captured.append({"path": request.url.path, "body": body})
        assert request.url.path.endswith("/responses")
        return httpx.Response(
            200,
            json={
                "id": "resp_1",
                "output": [
                    {
                        "type": "reasoning",
                        "id": "rs_1",
                        "summary": [{"type": "summary_text", "text": "think"}],
                        "encrypted_content": "enc-from-openai",
                    },
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "hello"}],
                    },
                ],
                "usage": {"input_tokens": 3, "output_tokens": 2},
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-6.1-sol",
        api_key="sk-test",
        provider="openai",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1),
    )
    request = InternalRequest(
        model="daari",
        messages=[Message(role="user", content="hi")],
        meta=RequestMeta(anthropic_version="2023-06-01"),
        sampling=SamplingParams(thinking={"type": "enabled", "budget_tokens": 1024}),
    )
    result = await executor.execute(request, escalated_from="L5", local_confidence=0.1)
    assert result.content == "hello"
    assert result.reasoning_encrypted == "enc-from-openai"
    assert captured
    assert "reasoning.encrypted_content" in (captured[0]["body"].get("include") or [])


@pytest.mark.asyncio
async def test_openai_frontier_replays_encrypted_reasoning_on_followup():
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        captured.append(body)
        return httpx.Response(
            200,
            json={
                "id": "resp_2",
                "output": [
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "next"}],
                    }
                ],
                "usage": {"input_tokens": 5, "output_tokens": 1},
            },
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-6.1-sol",
        api_key="sk-test",
        provider="openai",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1),
    )
    packed = pack_encrypted_reasoning_block("enc-replay")
    request = InternalRequest(
        model="daari",
        messages=[
            Message(role="user", content="first"),
            Message(
                role="assistant",
                content="prior",
                thinking_blocks=[packed],
            ),
            Message(role="user", content="again"),
        ],
        meta=RequestMeta(anthropic_version="2023-06-01"),
    )
    result = await executor.execute(request, escalated_from="L5", local_confidence=0.1)
    assert result.content == "next"
    assert captured
    body = captured[0]
    assert "reasoning.encrypted_content" in (body.get("include") or [])
    items = body.get("input") or []
    reasoning = [i for i in items if isinstance(i, dict) and i.get("type") == "reasoning"]
    assert reasoning
    assert reasoning[0].get("encrypted_content") == "enc-replay"


@pytest.mark.asyncio
async def test_messages_nonstream_emits_redacted_thinking(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="answer",
            model="gpt-6.1-sol",
            daari_meta=DaariMeta(
                tier="L6", executor="frontier", provider_id="openai", latency_ms=1
            ),
            reasoning_encrypted="enc-out",
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"anthropic-version": "2023-06-01", "x-api-key": "test"},
        )
    assert resp.status_code == 200, resp.text
    content = resp.json()["content"]
    assert content[0]["type"] == "redacted_thinking"
    assert unpack_encrypted_reasoning(content[0]) == "enc-out"
    assert content[1] == {"type": "text", "text": "answer"}


@pytest.mark.asyncio
async def test_messages_stream_emits_redacted_thinking(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_stream(request, outcome=None):
        meta = {
            "tier": "L6",
            "executor": "frontier",
            "provider_id": "openai",
            "stream": True,
        }
        yield (
            "event: message_start\ndata: "
            + json.dumps(
                {
                    "type": "message_start",
                    "message": {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "model": "gpt-6.1-sol",
                        "content": [],
                        "stop_reason": None,
                        "stop_sequence": None,
                        "usage": {"input_tokens": 1, "output_tokens": 0},
                    },
                    "daari_meta": meta,
                }
            )
            + "\n\n"
        )
        packed = pack_encrypted_reasoning_block("enc-stream")
        yield (
            "event: content_block_start\ndata: "
            + json.dumps(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": packed,
                    "daari_meta": meta,
                }
            )
            + "\n\n"
        )
        yield (
            "event: content_block_stop\ndata: "
            + json.dumps({"type": "content_block_stop", "index": 0, "daari_meta": meta})
            + "\n\n"
        )
        yield (
            "event: content_block_start\ndata: "
            + json.dumps(
                {
                    "type": "content_block_start",
                    "index": 1,
                    "content_block": {"type": "text", "text": ""},
                    "daari_meta": meta,
                }
            )
            + "\n\n"
        )
        yield (
            "event: content_block_delta\ndata: "
            + json.dumps(
                {
                    "type": "content_block_delta",
                    "index": 1,
                    "delta": {"type": "text_delta", "text": "streamed"},
                    "daari_meta": meta,
                }
            )
            + "\n\n"
        )
        yield (
            "event: content_block_stop\ndata: "
            + json.dumps({"type": "content_block_stop", "index": 1, "daari_meta": meta})
            + "\n\n"
        )
        yield (
            "event: message_delta\ndata: "
            + json.dumps(
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1},
                    "daari_meta": meta,
                }
            )
            + "\n\n"
        )
        yield (
            "event: message_stop\ndata: "
            + json.dumps({"type": "message_stop", "daari_meta": meta})
            + "\n\n"
        )

    app.state.ctx.router.stream_anthropic_events = fake_stream
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/messages",
            json={
                "model": "daari",
                "max_tokens": 32,
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"anthropic-version": "2023-06-01", "x-api-key": "test"},
        )
    assert resp.status_code == 200, resp.text
    assert "redacted_thinking" in resp.text
    assert f"{DAARI_ENCRYPTED_REASONING_PREFIX}enc-stream" in resp.text


@pytest.mark.asyncio
async def test_openai_frontier_stream_yields_encrypted_reasoning_event():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode())
        assert "reasoning.encrypted_content" in (body.get("include") or [])
        # Minimal Responses SSE: reasoning item done, then text delta, then completed.
        frames = [
            {
                "type": "response.output_item.done",
                "item": {
                    "type": "reasoning",
                    "id": "rs_s",
                    "encrypted_content": "enc-sse",
                    "summary": [],
                },
            },
            {
                "type": "response.output_text.delta",
                "delta": "hi",
            },
            {"type": "response.completed"},
        ]
        lines = "".join(f"data: {json.dumps(f)}\n\n" for f in frames)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=lines.encode(),
        )

    executor = FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model="gpt-6.1-sol",
        api_key="sk-test",
        provider="openai",
        transport=httpx.MockTransport(handler),
        retry=RetryPolicy(attempts=1),
    )
    request = InternalRequest(
        model="daari",
        messages=[Message(role="user", content="hi")],
        meta=RequestMeta(anthropic_version="2023-06-01"),
        sampling=SamplingParams(thinking={"type": "enabled", "budget_tokens": 256}),
    )
    events: list = []
    async for event in executor.stream(request, escalated_from="L5", local_confidence=0.1):
        events.append(event)
    assert {"reasoning_encrypted": "enc-sse"} in events
    assert "hi" in events

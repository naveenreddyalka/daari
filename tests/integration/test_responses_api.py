"""OpenAI Responses API adapter (issue #108)."""

from __future__ import annotations

import json

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.gateway.responses import (
    ResponsesRequest,
    responses_input_to_messages,
    responses_tools_to_openai,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


def _mock_route(app, content="routed answer"):
    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.last_request = request
        return InternalResponse(
            content=content,
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=5),
        )

    app.state.ctx.router.route = fake_route
    return fake_route


class TestInputMapping:
    def test_string_input_becomes_user_message(self):
        body = ResponsesRequest(model="daari", input="hello there")
        messages = responses_input_to_messages(body)
        assert [(m.role, m.content) for m in messages] == [("user", "hello there")]

    def test_instructions_become_leading_system(self):
        body = ResponsesRequest(model="daari", input="hi", instructions="Be terse.")
        messages = responses_input_to_messages(body)
        assert messages[0].role == "system"
        assert messages[0].content == "Be terse."

    def test_item_list_with_typed_parts(self):
        body = ResponsesRequest(
            model="daari",
            input=[
                {"type": "message", "role": "user", "content": [
                    {"type": "input_text", "text": "part one "},
                    {"type": "input_text", "text": "part two"},
                ]},
                {"type": "message", "role": "assistant", "content": "earlier answer"},
                {"type": "function_call", "name": "ignored"},  # out of scope: skipped
            ],
        )
        messages = responses_input_to_messages(body)
        assert [(m.role, m.content) for m in messages] == [
            ("user", "part one part two"),
            ("assistant", "earlier answer"),
        ]

    def test_flat_tools_convert_to_nested(self):
        converted = responses_tools_to_openai(
            [{"type": "function", "name": "get_weather", "parameters": {"type": "object"}}]
        )
        assert converted[0]["function"]["name"] == "get_weather"


@pytest.mark.asyncio
async def test_non_stream_response_shape(settings):
    app = _app(settings)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses", json={"model": "daari", "input": "say hi"}
        )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "response"
    assert body["status"] == "completed"
    assert body["output"][0]["type"] == "message"
    assert body["output"][0]["content"][0] == {
        "type": "output_text",
        "text": "routed answer",
        "annotations": [],
    }
    assert body["usage"]["output_tokens"] >= 1
    assert "daari_meta" not in body  # opt-in via X-Daari-Meta


@pytest.mark.asyncio
async def test_meta_header_includes_daari_meta_and_routing_headers_apply(settings):
    app = _app(settings)
    fake = _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "say hi"},
            headers={
                "X-Daari-Meta": "true",
                "X-Daari-No-Frontier": "true",
                "X-Daari-Tier-Cap": "L4",
            },
        )
    assert response.json()["daari_meta"]["tier"] == "L3"
    assert fake.last_request.meta.no_frontier is True
    assert fake.last_request.meta.tier_cap == "L4"


@pytest.mark.asyncio
async def test_empty_input_is_400(settings):
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/responses", json={"model": "daari", "input": []})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_stream_emits_responses_event_sequence(settings):
    app = _app(settings)

    async def fake_chunks(request: InternalRequest):
        for piece in ("Hello", " world"):
            chunk = {"choices": [{"delta": {"content": piece}}]}
            yield f"data: {json.dumps(chunk)}\n\n"
        yield "data: [DONE]\n\n"

    app.state.ctx.router.stream_openai_chunks = fake_chunks
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses", json={"model": "daari", "input": "say hi", "stream": True}
        )
    assert response.status_code == 200
    text = response.text
    events = [line.split(" ", 1)[1] for line in text.splitlines() if line.startswith("event: ")]
    assert events[0] == "response.created"
    assert events[-1] == "response.completed"
    assert events.count("response.output_text.delta") == 2
    assert '"delta": "Hello"' in text
    completed = json.loads(text.split("event: response.completed\ndata: ", 1)[1].split("\n")[0])
    assert completed["response"]["output"][0]["content"][0]["text"] == "Hello world"


@pytest.mark.asyncio
async def test_stream_failure_emits_response_failed(settings):
    app = _app(settings)

    async def broken_chunks(request: InternalRequest):
        yield 'data: {"choices": [{"delta": {"content": "par"}}]}\n\n'
        raise RuntimeError("tier exploded")

    app.state.ctx.router.stream_openai_chunks = broken_chunks
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses", json={"model": "daari", "input": "say hi", "stream": True}
        )
    assert "event: response.failed" in response.text
    assert "tier exploded" in response.text

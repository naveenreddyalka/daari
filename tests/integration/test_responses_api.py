"""OpenAI Responses API adapter (issue #108)."""

from __future__ import annotations

import json

import httpx
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
                {
                    "type": "function_call",
                    "call_id": "call_1",
                    "name": "lookup",
                    "arguments": "{\"q\": \"x\"}",
                },
                {
                    "type": "function_call_output",
                    "call_id": "call_1",
                    "output": "found it",
                },
            ],
        )
        messages = responses_input_to_messages(body)
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[2].role == "assistant"
        assert messages[2].tool_calls[0]["function"]["name"] == "lookup"
        assert messages[3].role == "tool"
        assert messages[3].tool_call_id == "call_1"
        assert messages[3].content == "found it"

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


def _mock_route_with_tools(app):
    async def fake_route(request: InternalRequest) -> InternalResponse:
        fake_route.last_request = request
        return InternalResponse(
            content="",
            model="llama3.2:3b",
            finish_reason="tool_calls",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=5),
            tool_calls=[
                {
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "get_weather", "arguments": "{\"city\": \"NYC\"}"},
                }
            ],
        )

    app.state.ctx.router.route = fake_route
    return fake_route


@pytest.mark.asyncio
async def test_function_call_output_item_is_emitted(settings):
    app = _app(settings)
    _mock_route_with_tools(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "weather?",
                "tools": [{"type": "function", "name": "get_weather", "parameters": {"type": "object"}}],
            },
        )
    assert response.status_code == 200
    items = response.json()["output"]
    call = next(item for item in items if item["type"] == "function_call")
    assert call["name"] == "get_weather"
    assert call["call_id"] == "call_abc"
    assert json.loads(call["arguments"]) == {"city": "NYC"}


@pytest.mark.asyncio
async def test_stream_emits_function_call_argument_deltas(settings):
    app = _app(settings)

    async def fake_chunks(request: InternalRequest):
        delta = {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "lookup", "arguments": "{\"q\":"},
                }
            ]
        }
        yield f"data: {json.dumps({'choices': [{'delta': delta}]})}\n\n"
        delta2 = {"tool_calls": [{"index": 0, "function": {"arguments": " \"x\"}"}}]}
        yield f"data: {json.dumps({'choices': [{'delta': delta2}]})}\n\n"
        yield "data: [DONE]\n\n"

    app.state.ctx.router.stream_openai_chunks = fake_chunks
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses", json={"model": "daari", "input": "lookup x", "stream": True}
        )
    text = response.text
    assert "response.function_call_arguments.delta" in text
    assert "response.function_call_arguments.done" in text


@pytest.mark.asyncio
async def test_previous_response_id_chains_conversation(settings):
    app = _app(settings)
    fake = _mock_route(app, content="second turn")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post("/v1/responses", json={"model": "daari", "input": "hello"})
        first_id = first.json()["id"]
        second = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "and then?", "previous_response_id": first_id},
        )
    assert second.status_code == 200
    roles = [m.role for m in fake.last_request.messages]
    assert "assistant" in roles
    assert any(m.content == "hello" for m in fake.last_request.messages)


@pytest.mark.asyncio
async def test_store_false_is_not_retrievable(settings):
    app = _app(settings)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses", json={"model": "daari", "input": "ephemeral", "store": False}
        )
        fetched = await client.get(f"/v1/responses/{created.json()['id']}")
    assert created.status_code == 200
    assert fetched.status_code == 404


@pytest.mark.asyncio
async def test_stored_response_is_retrievable(settings):
    app = _app(settings)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post("/v1/responses", json={"model": "daari", "input": "keep me"})
        fetched = await client.get(f"/v1/responses/{created.json()['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["output"][0]["content"][0]["text"] == "routed answer"


@pytest.mark.asyncio
async def test_background_returns_queued_then_completes(settings):
    app = _app(settings)
    _mock_route(app, content="done in background")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses", json={"model": "daari", "input": "later", "background": True}
        )
        assert created.status_code == 200
        assert created.json()["status"] == "queued"
        response_id = created.json()["id"]
        body = None
        for _ in range(20):
            fetched = await client.get(f"/v1/responses/{response_id}")
            body = fetched.json()
            if body.get("status") == "completed":
                break
        assert body["status"] == "completed"
        assert body["output"][0]["content"][0]["text"] == "done in background"


@pytest.mark.asyncio
async def test_include_is_rejected_not_dropped(settings):
    app = _app(settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "hi", "include": ["file_search_call.results"]},
        )
    assert response.status_code == 400
    assert "include" in response.text.lower()


@pytest.mark.asyncio
async def test_metadata_is_echoed(settings):
    app = _app(settings)
    _mock_route(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "hi", "metadata": {"run": "a1"}},
        )
    assert response.status_code == 200
    assert response.json()["metadata"] == {"run": "a1"}


@pytest.mark.asyncio
async def test_openai_sdk_responses_client(settings):
    openai = pytest.importorskip("openai")
    app = _app(settings)
    _mock_route(app, content="sdk-ok")
    http = httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    client = openai.AsyncOpenAI(base_url="http://test/v1", api_key="local", http_client=http)
    created = await client.responses.create(model="daari", input="hello from sdk")
    assert created.status == "completed"
    assert created.output[0].content[0].text == "sdk-ok"
    fetched = await client.responses.retrieve(created.id)
    assert fetched.id == created.id
    await http.aclose()

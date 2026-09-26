"""Responses API reasoning items across previous_response_id turns (#1133)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.responses import (
    ResponsesRequest,
    _SUPPORTED_INCLUDES,
    _conversation_after,
    _output_items_from_result,
    responses_input_to_messages,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def test_reasoning_input_items_become_assistant_thinking_blocks():
    body = ResponsesRequest(
        model="daari",
        input=[
            {"type": "message", "role": "user", "content": "plan this"},
            {
                "type": "reasoning",
                "id": "rs_prior",
                "summary": [{"type": "summary_text", "text": "first I sketch a plan"}],
            },
            {"type": "message", "role": "assistant", "content": "here is the plan"},
        ],
    )
    messages = responses_input_to_messages(body)
    assert messages[0].role == "user"
    assert messages[1].role == "assistant"
    assert messages[1].content in ("", None)
    assert messages[1].thinking_blocks
    assert messages[1].thinking_blocks[0]["type"] == "reasoning"
    assert messages[1].thinking_blocks[0]["id"] == "rs_prior"
    assert "first I sketch a plan" in str(messages[1].thinking_blocks[0]["summary"])
    assert messages[2].role == "assistant"
    assert messages[2].content == "here is the plan"


def test_output_includes_reasoning_item_when_result_has_reasoning_content():
    result = InternalResponse(
        content="final answer",
        model="gpt-4o",
        daari_meta=DaariMeta(tier="L6", executor="openai", latency_ms=1),
        reasoning_content="chain of thought",
    )
    items = _output_items_from_result(result)
    assert items[0]["type"] == "reasoning"
    assert items[0]["summary"][0]["text"] == "chain of thought"
    assert items[1]["type"] == "message"
    assert items[1]["content"][0]["text"] == "final answer"


def test_non_reasoning_output_unchanged():
    result = InternalResponse(
        content="plain",
        model="llama",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )
    items = _output_items_from_result(result)
    assert [item["type"] for item in items] == ["message"]
    assert items[0]["content"][0]["text"] == "plain"


def test_conversation_after_persists_reasoning_for_replay():
    messages = [Message(role="user", content="hi")]
    output = [
        {
            "type": "reasoning",
            "id": "rs_1",
            "summary": [{"type": "summary_text", "text": "think hard"}],
        },
        {
            "type": "message",
            "id": "msg_1",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "hello", "annotations": []}],
        },
    ]
    history = _conversation_after(messages, output)
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"
    assert history[1]["thinking_blocks"][0]["type"] == "reasoning"
    assert history[2]["role"] == "assistant"
    assert history[2]["content"] == "hello"


def test_supported_includes_allowlist_contains_encrypted_content():
    assert "reasoning.encrypted_content" in _SUPPORTED_INCLUDES


@pytest.mark.asyncio
async def test_include_unsupported_names_allowlist(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="x",
            model="m",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "include": ["file_search_call.results"],
            },
        )
    assert denied.status_code == 400
    detail = denied.json()["detail"]
    assert "include is not supported" in detail
    assert "supported:" in detail
    assert "file_search_call.results" in detail
    assert "reasoning.encrypted_content" in detail


@pytest.mark.asyncio
async def test_include_reasoning_encrypted_content_accepted(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)

    async def fake_route(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="answer",
            model="m",
            daari_meta=DaariMeta(tier="L6", executor="openai", latency_ms=1),
            reasoning_content="secret thoughts",
            reasoning_encrypted="enc-blob",
        )

    app.state.ctx.router.route = fake_route
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        without = await client.post("/v1/responses", json={"model": "daari", "input": "hi"})
        with_inc = await client.post(
            "/v1/responses",
            json={
                "model": "daari",
                "input": "hi",
                "include": ["reasoning.encrypted_content"],
            },
        )
    assert without.status_code == 200, without.text
    assert with_inc.status_code == 200, with_inc.text
    out_plain = without.json()["output"]
    reasoning_plain = next(i for i in out_plain if i["type"] == "reasoning")
    assert "encrypted_content" not in reasoning_plain
    out_enc = with_inc.json()["output"]
    reasoning_enc = next(i for i in out_enc if i["type"] == "reasoning")
    assert reasoning_enc.get("encrypted_content") == "enc-blob"

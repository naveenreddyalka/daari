"""Preserve Anthropic thinking blocks for L6 replay (issue #431)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.anthropic import AnthropicMessageIn, anthropic_message_to_internal, wants_anthropic_models
from daari.gateway.content import content_to_text, extract_thinking_blocks, sanitize_messages_for_ollama
from daari.gateway.internal import InternalRequest, Message
from daari.router.anthropic_messages import to_anthropic_payload
from daari.router.capabilities import anthropic_model_cards, anthropic_models_payload
from daari.router.router import AppContext
from daari.server.app import create_app


class _FakeRequest:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


def test_wants_anthropic_models_header_and_x_api_key() -> None:
    assert wants_anthropic_models(_FakeRequest({"anthropic-version": "2023-06-01"})) is True
    assert wants_anthropic_models(_FakeRequest({"x-api-key": "sekret"})) is True
    assert wants_anthropic_models(_FakeRequest({"authorization": "Bearer sekret"})) is False
    assert wants_anthropic_models(_FakeRequest({})) is False
    # Bearer wins over x-api-key for OpenAI-shaped clients that send both.
    assert (
        wants_anthropic_models(
            _FakeRequest({"x-api-key": "sekret", "authorization": "Bearer sekret"})
        )
        is False
    )


def test_anthropic_model_cards_match_openai_ids(settings) -> None:
    from daari.router.capabilities import openai_model_cards

    openai_ids = [card["id"] for card in openai_model_cards(settings)]
    anthropic = anthropic_model_cards(settings)
    assert [card["id"] for card in anthropic] == openai_ids
    assert all(card["type"] == "model" for card in anthropic)
    assert all(card["display_name"] for card in anthropic)
    assert all(card["created_at"].endswith("Z") for card in anthropic)
    payload = anthropic_models_payload(settings)
    assert payload["has_more"] is False
    assert payload["first_id"] == anthropic[0]["id"]
    assert payload["last_id"] == anthropic[-1]["id"]


@pytest.mark.asyncio
async def test_models_list_anthropic_shape_via_header(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get(
            "/v1/models", headers={"anthropic-version": "2023-06-01"}
        )
        via_key = await client.get("/v1/models", headers={"x-api-key": "unused-when-open"})
        openai_shape = await client.get("/v1/models")
    assert response.status_code == 200
    body = response.json()
    assert "object" not in body
    assert body["has_more"] is False
    assert body["data"]
    assert body["data"][0]["type"] == "model"
    assert "display_name" in body["data"][0]
    assert "created_at" in body["data"][0]
    assert via_key.json()["data"][0]["type"] == "model"
    assert openai_shape.json()["object"] == "list"
    assert "capabilities" in openai_shape.json()["data"][0]


def test_extract_keeps_thinking_with_text() -> None:
    blocks = [
        {"type": "thinking", "thinking": "step by step", "signature": "sig_abc"},
        {"type": "text", "text": "answer"},
    ]
    kept = extract_thinking_blocks(blocks)
    assert kept == [
        {"type": "thinking", "thinking": "step by step", "signature": "sig_abc"},
    ]


def test_extract_keeps_signature_only_thinking() -> None:
    """Omitted-display blocks have empty thinking but a required signature."""
    blocks = [{"type": "thinking", "thinking": "", "signature": "sig_only"}]
    assert extract_thinking_blocks(blocks) == [
        {"type": "thinking", "thinking": "", "signature": "sig_only"},
    ]


def test_extract_omits_empty_thinking() -> None:
    blocks = [
        {"type": "thinking", "thinking": "", "signature": ""},
        {"type": "thinking", "thinking": "   "},
        {"type": "text", "text": "hi"},
    ]
    assert extract_thinking_blocks(blocks) == []


def test_extract_keeps_redacted_thinking_with_data() -> None:
    blocks = [{"type": "redacted_thinking", "data": "enc_blob"}]
    assert extract_thinking_blocks(blocks) == [
        {"type": "redacted_thinking", "data": "enc_blob"},
    ]


def test_extract_omits_empty_redacted_thinking() -> None:
    assert extract_thinking_blocks([{"type": "redacted_thinking", "data": ""}]) == []
    assert extract_thinking_blocks([{"type": "redacted_thinking"}]) == []


def test_content_to_text_ignores_thinking() -> None:
    blocks = [
        {"type": "thinking", "thinking": "secret chain", "signature": "sig"},
        {"type": "text", "text": "visible"},
    ]
    assert content_to_text(blocks) == "visible"


def test_anthropic_inbound_keeps_thinking_on_message() -> None:
    message = AnthropicMessageIn(
        role="assistant",
        content=[
            {"type": "thinking", "thinking": "plan", "signature": "sig_1"},
            {"type": "text", "text": "done"},
        ],
    )
    expanded = anthropic_message_to_internal(message)
    assert len(expanded) == 1
    assert expanded[0].content == "done"
    assert expanded[0].thinking_blocks == [
        {"type": "thinking", "thinking": "plan", "signature": "sig_1"},
    ]


def test_anthropic_inbound_omits_empty_thinking() -> None:
    message = AnthropicMessageIn(
        role="assistant",
        content=[
            {"type": "thinking", "thinking": "", "signature": ""},
            {"type": "text", "text": "hi"},
        ],
    )
    expanded = anthropic_message_to_internal(message)
    assert expanded[0].thinking_blocks == []
    assert expanded[0].content == "hi"


def test_anthropic_inbound_thinking_with_tool_use() -> None:
    message = AnthropicMessageIn(
        role="assistant",
        content=[
            {"type": "thinking", "thinking": "", "signature": "sig_tool"},
            {"type": "text", "text": "calling"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "search",
                "input": {"q": "x"},
            },
        ],
    )
    expanded = anthropic_message_to_internal(message)
    assert expanded[0].thinking_blocks[0]["signature"] == "sig_tool"
    assert expanded[0].tool_calls is not None
    assert expanded[0].content == "calling"


def test_l6_replay_emits_thinking_before_text() -> None:
    request = InternalRequest(
        messages=[
            Message(role="user", content="q"),
            Message(
                role="assistant",
                content="a",
                thinking_blocks=[
                    {"type": "thinking", "thinking": "reason", "signature": "sig"},
                ],
            ),
        ],
        model="daari",
    )
    payload = to_anthropic_payload(request, model="claude-sonnet-4-0")
    assistant = payload["messages"][1]
    assert assistant["content"][0] == {
        "type": "thinking",
        "thinking": "reason",
        "signature": "sig",
    }
    assert assistant["content"][1] == {"type": "text", "text": "a"}


def test_l6_replay_emits_thinking_before_tool_use() -> None:
    request = InternalRequest(
        messages=[
            Message(role="user", content="search"),
            Message(
                role="assistant",
                content="ok",
                thinking_blocks=[
                    {"type": "thinking", "thinking": "", "signature": "sig_t"},
                    {"type": "redacted_thinking", "data": "blob"},
                ],
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": '{"q": "x"}'},
                    }
                ],
            ),
        ],
        model="daari",
    )
    payload = to_anthropic_payload(request, model="claude-sonnet-4-0")
    content = payload["messages"][1]["content"]
    assert content[0]["type"] == "thinking"
    assert content[1]["type"] == "redacted_thinking"
    assert content[2]["type"] == "text"
    assert content[3]["type"] == "tool_use"


def test_sanitize_strips_thinking_for_ollama() -> None:
    messages = [
        Message(
            role="assistant",
            content="answer",
            thinking_blocks=[
                {"type": "thinking", "thinking": "hidden", "signature": "sig"},
            ],
        )
    ]
    sanitized = sanitize_messages_for_ollama(messages)
    assert sanitized[0].thinking_blocks == []
    assert sanitized[0].content == "answer"

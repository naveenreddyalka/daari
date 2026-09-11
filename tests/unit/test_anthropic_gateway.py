"""Preserve Anthropic thinking blocks for L6 replay (issue #431)."""

from __future__ import annotations

from daari.gateway.anthropic import AnthropicMessageIn, anthropic_message_to_internal
from daari.gateway.content import content_to_text, extract_thinking_blocks, sanitize_messages_for_ollama
from daari.gateway.internal import InternalRequest, Message
from daari.router.anthropic_messages import to_anthropic_payload


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

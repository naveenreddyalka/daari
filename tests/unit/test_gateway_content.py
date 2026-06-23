from __future__ import annotations

from daari.gateway.content import content_to_text, sanitize_messages_for_ollama
from daari.gateway.internal import Message


def test_content_to_text_string() -> None:
    assert content_to_text("hello") == "hello"


def test_content_to_text_array() -> None:
    blocks = [{"type": "text", "text": "What is 2 plus 2?"}]
    assert content_to_text(blocks) == "What is 2 plus 2?"


def test_content_to_text_cursor_input_text() -> None:
    blocks = [{"type": "input_text", "text": "Debug this module"}]
    assert content_to_text(blocks) == "Debug this module"


def test_content_to_text_none() -> None:
    assert content_to_text(None) is None


def test_content_to_text_empty_array() -> None:
    assert content_to_text([]) is None


def test_sanitize_messages_strips_tool_calls() -> None:
    messages = [
        Message(role="user", content="run grep"),
        Message(
            role="assistant",
            content=None,
            tool_calls=[{"id": "1", "type": "function", "function": {"name": "grep", "arguments": "{}"}}],
        ),
        Message(role="user", content="thanks"),
    ]
    sanitized = sanitize_messages_for_ollama(messages)
    assert sanitized[1].tool_calls is None
    assert "grep" in (sanitized[1].content or "")


def test_sanitize_messages_converts_tool_role() -> None:
    messages = [Message(role="tool", content="found 3 matches", tool_calls=None)]
    sanitized = sanitize_messages_for_ollama(messages)
    assert sanitized[0].role == "user"
    assert "found 3 matches" in (sanitized[0].content or "")


def test_content_to_text_input_text() -> None:
    blocks = [{"type": "input_text", "text": "what is two plus two?"}]
    assert content_to_text(blocks) == "what is two plus two?"


def test_content_to_text_single_dict() -> None:
    block = {"type": "text", "text": "hello"}
    assert content_to_text(block) == "hello"

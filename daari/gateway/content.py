from __future__ import annotations

from typing import Any

from daari.gateway.internal import Message

_TEXT_BLOCK_TYPES = frozenset({"text", "input_text", "output_text"})


def content_to_text(content: str | list[dict[str, Any]] | dict[str, Any] | None) -> str | None:
    """Normalize OpenAI/Anthropic/Cursor message content to plain text."""
    if content is None:
        return None
    if isinstance(content, str):
        stripped = content.strip()
        return stripped or None
    if isinstance(content, dict):
        return content_to_text([content])
    text_parts: list[str] = []
    for block in content:
        block_type = block.get("type")
        if block_type in _TEXT_BLOCK_TYPES and isinstance(block.get("text"), str):
            text_parts.append(block["text"])
            continue
        # Cursor sometimes nests text under content/value keys.
        for key in ("text", "content", "value"):
            value = block.get(key)
            if isinstance(value, str) and value.strip():
                text_parts.append(value.strip())
                break
    joined = "\n".join(part for part in text_parts if part)
    return joined or None


def _tool_call_names(tool_calls: list[Any]) -> list[str]:
    names: list[str] = []
    for tool_call in tool_calls:
        if not isinstance(tool_call, dict):
            continue
        function = tool_call.get("function")
        if isinstance(function, dict) and function.get("name"):
            names.append(str(function["name"]))
    return names


def sanitize_messages_for_ollama(messages: list[Message]) -> list[Message]:
    """Drop tool protocol fields so local Ollama chat gets plain text history."""
    sanitized: list[Message] = []
    for message in messages:
        if message.role == "tool":
            if message.content:
                sanitized.append(Message(role="user", content=f"[Tool result]\n{message.content}"))
            continue
        if message.tool_calls:
            text = (message.content or "").strip()
            if not text:
                names = _tool_call_names(message.tool_calls)
                text = f"(called tools: {', '.join(names)})" if names else "(called tools)"
            sanitized.append(Message(role=message.role, content=text))
            continue
        sanitized.append(message)
    return sanitized

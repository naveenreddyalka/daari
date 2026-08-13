from __future__ import annotations

from typing import Any

from daari.gateway.internal import ContentImage, Message

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


def extract_images(content: str | list[dict[str, Any]] | dict[str, Any] | None) -> list[ContentImage]:
    """Pull image blocks out of an OpenAI/Anthropic/Ollama content value.

    `content_to_text` is deliberately text-only — callers that need the pictures
    have to ask for them, or they vanish the way they did before #164.
    """
    if content is None or isinstance(content, str):
        return []
    blocks = [content] if isinstance(content, dict) else content
    images: list[ContentImage] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type in {"image_url", "input_image"}:
            image_url = block.get("image_url") or block.get("url")
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if isinstance(url, str) and url:
                images.append(_image_from_url(url))
        elif block_type == "image":
            source = block.get("source") or {}
            if not isinstance(source, dict):
                continue
            if source.get("type") == "base64" and isinstance(source.get("data"), str):
                images.append(
                    ContentImage(
                        media_type=str(source.get("media_type") or "image/png"),
                        data=source["data"],
                    )
                )
            elif isinstance(source.get("url"), str):
                images.append(_image_from_url(source["url"]))
    return images


def _image_from_url(url: str) -> ContentImage:
    if url.startswith("data:") and "," in url:
        header, data = url.split(",", 1)
        media = "image/png"
        rest = header[5:] if header.startswith("data:") else header
        if ";" in rest:
            media = rest.split(";", 1)[0] or media
        return ContentImage(media_type=media, data=data, url=url)
    return ContentImage(url=url)


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
            sanitized.append(Message(role=message.role, content=text, images=list(message.images)))
            continue
        sanitized.append(
            Message(role=message.role, content=message.content, images=list(message.images))
        )
    return sanitized

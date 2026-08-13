"""Convert InternalRequest to Anthropic's /v1/messages shape (issue #166)."""

from __future__ import annotations

import json
from typing import Any

from daari.gateway.internal import InternalRequest, Message
from daari.observability.trace import add_step

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


def infer_frontier_kind(provider: str, base_url: str = "") -> str:
    if (provider or "").lower() in {"anthropic", "claude"}:
        return "anthropic"
    if "anthropic.com" in (base_url or "").lower():
        return "anthropic"
    return "openai"


def anthropic_messages_path(base_url: str) -> str:
    stripped = (base_url or "").rstrip("/")
    if stripped.endswith("/v1"):
        return "/messages"
    return "/v1/messages"


def anthropic_headers(api_key: str) -> dict[str, str]:
    return {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }


def openai_tools_to_anthropic(tools: list[Any] | None) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if tool.get("type") == "function" else tool
        if not isinstance(function, dict) or not function.get("name"):
            continue
        converted.append(
            {
                "name": function["name"],
                "description": function.get("description") or "",
                "input_schema": function.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return converted


def to_anthropic_payload(
    request: InternalRequest,
    *,
    model: str,
    stream: bool = False,
    prompt_cache: bool = False,
) -> dict[str, Any]:
    system_blocks: list[dict[str, Any]] = []
    converted: list[dict[str, Any]] = []
    pending_results: list[dict[str, Any]] = []

    def flush_results() -> None:
        nonlocal pending_results
        if pending_results:
            converted.append({"role": "user", "content": pending_results})
            pending_results = []

    for message in request.messages:
        if message.role == "system":
            if message.content:
                system_blocks.append({"type": "text", "text": message.content})
            continue
        if message.role == "tool":
            pending_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id or "toolu_unknown",
                    "content": message.content or "",
                }
            )
            continue
        flush_results()
        converted.append(_conversation_message(message))

    flush_results()
    if not converted:
        converted = [{"role": "user", "content": " "}]

    if prompt_cache and system_blocks:
        system_blocks[-1] = {**system_blocks[-1], "cache_control": {"type": "ephemeral"}}
        add_step("prompt_cache_hint", provider="anthropic", marked_blocks=1)

    payload: dict[str, Any] = {
        "model": model,
        "messages": converted,
        "max_tokens": request.sampling.max_tokens or DEFAULT_MAX_TOKENS,
        "stream": stream,
    }
    if system_blocks:
        payload["system"] = system_blocks
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.tools:
        anthropic_tools = openai_tools_to_anthropic(request.tools)
        if anthropic_tools:
            payload["tools"] = anthropic_tools
    if request.sampling.top_p is not None:
        payload["top_p"] = request.sampling.top_p
    if request.sampling.stop:
        payload["stop_sequences"] = list(request.sampling.stop)
    return payload


def _conversation_message(message: Message) -> dict[str, Any]:
    role = message.role if message.role in {"user", "assistant"} else "user"
    if message.tool_calls:
        return {"role": "assistant", "content": _assistant_tool_content(message)}
    return {"role": role, "content": _parts(message)}


def _assistant_tool_content(message: Message) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if message.content:
        blocks.append({"type": "text", "text": message.content})
    for call in message.tool_calls or []:
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
        blocks.append(
            {
                "type": "tool_use",
                "id": call.get("id") or "toolu_unknown",
                "name": function.get("name") or "",
                "input": arguments if isinstance(arguments, dict) else {},
            }
        )
    return blocks or [{"type": "text", "text": ""}]


def _parts(message: Message) -> str | list[dict[str, Any]]:
    if not message.images:
        return message.content or ""
    parts: list[dict[str, Any]] = []
    if message.content:
        parts.append({"type": "text", "text": message.content})
    for image in message.images:
        data = image.as_base64()
        if not data:
            continue
        parts.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image.media_type or "image/png",
                    "data": data,
                },
            }
        )
    return parts or (message.content or "")


def text_from_anthropic_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text") or "")
    return "".join(parts)


def text_delta_from_sse_data(data: str) -> str | None:
    try:
        payload = json.loads(data)
    except ValueError:
        return None
    if payload.get("type") != "content_block_delta":
        return None
    delta = payload.get("delta") or {}
    if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
        return delta["text"]
    return None

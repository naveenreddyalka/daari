"""OpenAI encrypted reasoning ↔ Anthropic redacted_thinking for /v1/messages (#2214).

LiteLLM-parity: Responses ``reasoning.encrypted_content`` is packed into a
``redacted_thinking`` block Claude Code can echo, then unpacked back into a
Responses ``reasoning`` input item on the next OpenAI turn. Blocks signed with
``daari_encrypted_reasoning:`` are never forwarded to Anthropic or local tiers.
"""

from __future__ import annotations

from typing import Any

from daari.gateway.internal import InternalRequest, Message

DAARI_ENCRYPTED_REASONING_PREFIX = "daari_encrypted_reasoning:"


def pack_encrypted_reasoning_block(encrypted: str) -> dict[str, Any]:
    """Anthropic-shaped block that carries opaque OpenAI encrypted reasoning."""
    return {
        "type": "redacted_thinking",
        "data": f"{DAARI_ENCRYPTED_REASONING_PREFIX}{encrypted}",
    }


def is_openai_encrypted_reasoning_block(block: dict[str, Any] | None) -> bool:
    if not isinstance(block, dict):
        return False
    if block.get("type") == "reasoning" and isinstance(block.get("encrypted_content"), str):
        return bool(str(block["encrypted_content"]).strip())
    data = block.get("data")
    if block.get("type") == "redacted_thinking" and isinstance(data, str):
        return data.startswith(DAARI_ENCRYPTED_REASONING_PREFIX)
    signature = block.get("signature")
    if block.get("type") == "thinking" and isinstance(signature, str):
        return signature.startswith(DAARI_ENCRYPTED_REASONING_PREFIX)
    return False


def unpack_encrypted_reasoning(block: dict[str, Any] | None) -> str | None:
    if not isinstance(block, dict):
        return None
    if block.get("type") == "reasoning":
        encrypted = block.get("encrypted_content")
        return encrypted.strip() if isinstance(encrypted, str) and encrypted.strip() else None
    for key in ("data", "signature"):
        value = block.get(key)
        if isinstance(value, str) and value.startswith(DAARI_ENCRYPTED_REASONING_PREFIX):
            payload = value[len(DAARI_ENCRYPTED_REASONING_PREFIX) :]
            return payload or None
    return None


def strip_openai_encrypted_reasoning(messages: list[Message]) -> None:
    """Drop OpenAI-opaque reasoning blocks in place (Anthropic / local safety)."""
    for message in messages:
        if not message.thinking_blocks:
            continue
        kept = [
            block
            for block in message.thinking_blocks
            if isinstance(block, dict) and not is_openai_encrypted_reasoning_block(block)
        ]
        message.thinking_blocks = kept


def request_has_openai_encrypted_reasoning(request: InternalRequest) -> bool:
    for message in request.messages:
        for block in message.thinking_blocks or []:
            if is_openai_encrypted_reasoning_block(block):
                return True
    return False


def wants_openai_encrypted_reasoning(request: InternalRequest) -> bool:
    """True when a Messages→OpenAI hop should use Responses + encrypted include."""
    if request_has_openai_encrypted_reasoning(request):
        return True
    if getattr(request.meta, "anthropic_version", None) or getattr(
        request.meta, "anthropic_beta", None
    ):
        return True
    thinking = getattr(request.sampling, "thinking", None)
    return isinstance(thinking, dict) and bool(thinking)


def messages_to_responses_input(messages: list[Message]) -> list[dict[str, Any]]:
    """Convert internal messages into Responses ``input`` items, replaying encrypted reasoning."""
    items: list[dict[str, Any]] = []
    for message in messages:
        encrypted_blocks = [
            block
            for block in (message.thinking_blocks or [])
            if is_openai_encrypted_reasoning_block(block)
        ]
        for block in encrypted_blocks:
            encrypted = unpack_encrypted_reasoning(block)
            if not encrypted:
                continue
            item: dict[str, Any] = {
                "type": "reasoning",
                "encrypted_content": encrypted,
                "summary": block.get("summary") if isinstance(block.get("summary"), list) else [],
            }
            if isinstance(block.get("id"), str) and block["id"].strip():
                item["id"] = block["id"]
            items.append(item)
        if message.tool_calls:
            for call in message.tool_calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") if isinstance(call.get("function"), dict) else {}
                arguments = function.get("arguments") or "{}"
                if not isinstance(arguments, str):
                    import json

                    arguments = json.dumps(arguments)
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.get("id") or "call_unknown",
                        "name": function.get("name") or "",
                        "arguments": arguments,
                    }
                )
            if message.content:
                items.append(
                    {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": message.content}],
                    }
                )
            continue
        if message.role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id or "call_unknown",
                    "output": message.content or "",
                }
            )
            continue
        role = message.role if message.role in {"user", "assistant", "system"} else "user"
        content = message.content or ""
        if role == "assistant":
            items.append(
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": content}],
                }
            )
        else:
            items.append({"role": role, "content": content})
    return items


def reasoning_encrypted_from_responses_output(output: Any) -> str | None:
    if not isinstance(output, list):
        return None
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        encrypted = item.get("encrypted_content")
        if isinstance(encrypted, str) and encrypted.strip():
            return encrypted.strip()
    return None


def output_items_from_responses_output(output: Any) -> list[dict[str, Any]] | None:
    """Copy reasoning / function_call / message items in upstream order (#2298).

    Preserves every reasoning item (summary + encrypted_content) so the
    Responses facade can re-emit the same interleaving the model produced.
    """
    if not isinstance(output, list):
        return None
    items: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "reasoning":
            copied: dict[str, Any] = {
                "type": "reasoning",
                "id": item.get("id") or f"rs_{len(items)}",
                "summary": item.get("summary")
                if isinstance(item.get("summary"), list)
                else (
                    [{"type": "summary_text", "text": str(item.get("summary"))}]
                    if item.get("summary")
                    else []
                ),
            }
            encrypted = item.get("encrypted_content")
            if isinstance(encrypted, str) and encrypted.strip():
                copied["encrypted_content"] = encrypted.strip()
            items.append(copied)
        elif item_type == "function_call":
            items.append(
                {
                    "type": "function_call",
                    "id": item.get("id") or f"fc_{len(items)}",
                    "call_id": item.get("call_id") or item.get("id") or f"call_{len(items)}",
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "{}",
                    "status": item.get("status") or "completed",
                }
            )
        elif item_type == "message":
            items.append(
                {
                    "type": "message",
                    "id": item.get("id") or f"msg_{len(items)}",
                    "status": item.get("status") or "completed",
                    "role": item.get("role") or "assistant",
                    "content": item.get("content")
                    if item.get("content") is not None
                    else [{"type": "output_text", "text": "", "annotations": []}],
                }
            )
    return items or None


def text_from_responses_output(output: Any) -> str:
    if not isinstance(output, list):
        return ""
    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and isinstance(part.get("text"), str):
                parts.append(part["text"])
    return "".join(parts)


def tool_calls_from_responses_output(output: Any) -> list[dict[str, Any]] | None:
    if not isinstance(output, list):
        return None
    calls: list[dict[str, Any]] = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "function_call":
            continue
        calls.append(
            {
                "id": item.get("call_id") or item.get("id") or "call_unknown",
                "type": "function",
                "function": {
                    "name": item.get("name") or "",
                    "arguments": item.get("arguments") or "{}",
                },
            }
        )
    return calls or None


def anthropic_content_with_encrypted_reasoning(
    text: str,
    *,
    reasoning_encrypted: str | None = None,
    reasoning_content: str | None = None,
) -> list[dict[str, Any]]:
    """Build Messages ``content`` blocks, packing encrypted / plain thinking first."""
    blocks: list[dict[str, Any]] = []
    if isinstance(reasoning_encrypted, str) and reasoning_encrypted.strip():
        blocks.append(pack_encrypted_reasoning_block(reasoning_encrypted.strip()))
    elif isinstance(reasoning_content, str) and reasoning_content.strip():
        # Local-tier thinking (Ollama / OpenAI-compat) → Anthropic thinking (#2299).
        blocks.append({"type": "thinking", "thinking": reasoning_content.strip()})
    blocks.append({"type": "text", "text": text or ""})
    return blocks

"""Preserve every reasoning item and upstream Responses output order (#2298)."""

from __future__ import annotations

import pytest

from daari.gateway.internal import DaariMeta, InternalResponse, Message
from daari.gateway.responses import _conversation_after, _output_items_from_result
from daari.router.openai_encrypted_reasoning import (
    output_items_from_responses_output,
    reasoning_encrypted_from_responses_output,
)


def _interleaved_upstream() -> list[dict]:
    return [
        {
            "type": "reasoning",
            "id": "rs_1",
            "summary": [{"type": "summary_text", "text": "think about tool A"}],
            "encrypted_content": "enc-a",
        },
        {
            "type": "function_call",
            "id": "fc_1",
            "call_id": "call_a",
            "name": "tool_a",
            "arguments": "{}",
            "status": "completed",
        },
        {
            "type": "reasoning",
            "id": "rs_2",
            "summary": [{"type": "summary_text", "text": "think about tool B"}],
            "encrypted_content": "enc-b",
        },
        {
            "type": "function_call",
            "id": "fc_2",
            "call_id": "call_b",
            "name": "tool_b",
            "arguments": "{\"x\": 1}",
            "status": "completed",
        },
        {
            "type": "message",
            "id": "msg_1",
            "status": "completed",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "done", "annotations": []}],
        },
    ]


def test_output_items_from_responses_keeps_interleaved_order_and_both_encrypted():
    items = output_items_from_responses_output(_interleaved_upstream())
    assert items is not None
    assert [i["type"] for i in items] == [
        "reasoning",
        "function_call",
        "reasoning",
        "function_call",
        "message",
    ]
    assert items[0]["encrypted_content"] == "enc-a"
    assert items[0]["summary"][0]["text"] == "think about tool A"
    assert items[2]["encrypted_content"] == "enc-b"
    assert items[2]["summary"][0]["text"] == "think about tool B"
    assert items[1]["call_id"] == "call_a"
    assert items[3]["name"] == "tool_b"
    assert items[4]["content"][0]["text"] == "done"
    # Legacy helper still returns the first encrypted blob for flat field compat.
    assert reasoning_encrypted_from_responses_output(_interleaved_upstream()) == "enc-a"


def test_output_items_from_result_prefers_ordered_output_items():
    result = InternalResponse(
        content="done",
        model="gpt-5.6",
        daari_meta=DaariMeta(tier="L6", executor="frontier", latency_ms=1),
        tool_calls=[{"id": "call_a", "type": "function", "function": {"name": "tool_a", "arguments": "{}"}}],
        reasoning_content="only first would have been kept",
        reasoning_encrypted="enc-a",
        output_items=output_items_from_responses_output(_interleaved_upstream()),
    )
    plain = _output_items_from_result(result, include_encrypted=False)
    assert [i["type"] for i in plain] == [
        "reasoning",
        "function_call",
        "reasoning",
        "function_call",
        "message",
    ]
    assert "encrypted_content" not in plain[0]
    assert "encrypted_content" not in plain[2]
    enc = _output_items_from_result(result, include_encrypted=True)
    assert enc[0]["encrypted_content"] == "enc-a"
    assert enc[2]["encrypted_content"] == "enc-b"


def test_conversation_after_keeps_reasoning_adjacent_to_preceded_call():
    messages = [Message(role="user", content="go")]
    output = _output_items_from_result(
        InternalResponse(
            content="done",
            model="m",
            daari_meta=DaariMeta(tier="L6", executor="frontier", latency_ms=1),
            output_items=output_items_from_responses_output(_interleaved_upstream()),
        ),
        include_encrypted=True,
    )
    history = _conversation_after(messages, output)
    # user + reasoning + call + reasoning + call + message
    assert len(history) == 6
    assert history[1]["thinking_blocks"][0]["encrypted_content"] == "enc-a"
    assert history[2]["tool_calls"][0]["id"] == "call_a"
    assert history[3]["thinking_blocks"][0]["encrypted_content"] == "enc-b"
    assert history[4]["tool_calls"][0]["id"] == "call_b"
    assert history[5]["content"] == "done"


def test_flat_chat_shaped_result_unchanged():
    result = InternalResponse(
        content="hello",
        model="llama",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )
    items = _output_items_from_result(result)
    assert [i["type"] for i in items] == ["message"]
    assert items[0]["content"][0]["text"] == "hello"

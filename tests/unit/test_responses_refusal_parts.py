"""Responses input preserves assistant refusal parts (#2105)."""

from __future__ import annotations

from daari.gateway.internal import DaariMeta, InternalResponse
from daari.gateway.responses import (
    ResponsesRequest,
    _apply_dropped_content_warning,
    _content_to_text,
    responses_input_to_messages,
)


def test_content_to_text_preserves_refusal_part() -> None:
    content = [{"type": "refusal", "refusal": "I can't help with that."}]
    assert _content_to_text(content) == "I can't help with that."


def test_content_to_text_mixed_text_and_refusal_preserves_order() -> None:
    content = [
        {"type": "output_text", "text": "Earlier: "},
        {"type": "refusal", "refusal": "blocked"},
        {"type": "output_text", "text": " — ask differently."},
    ]
    assert _content_to_text(content) == "Earlier: blocked — ask differently."


def test_content_to_text_pure_text_unchanged() -> None:
    content = [
        {"type": "input_text", "text": "part one "},
        {"type": "input_text", "text": "part two"},
    ]
    assert _content_to_text(content) == "part one part two"


def test_responses_prior_assistant_refusal_reaches_internal_message() -> None:
    body = ResponsesRequest(
        model="daari",
        input=[
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "refusal", "refusal": "I must refuse."}],
            },
            {"type": "message", "role": "user", "content": "try again"},
        ],
    )
    messages = responses_input_to_messages(body)
    assert messages[0].role == "assistant"
    assert "I must refuse." in (messages[0].content or "")
    assert messages[1].content == "try again"


def test_old_flattening_empty_content_regression() -> None:
    """Pre-fix: refusal-only parts had no `text` key and flattened to ''."""
    content = [{"type": "refusal", "refusal": "nope"}]
    # Guard the bug shape: no `text` key on the part.
    assert "text" not in content[0]
    assert _content_to_text(content) != ""
    assert _content_to_text(content) == "nope"


def test_dropped_readable_input_file_is_reported() -> None:
    dropped: list[str] = []
    content = [
        {"type": "input_text", "text": "see attachment"},
        {"type": "input_file", "file_id": "file-abc", "filename": "notes.txt"},
    ]
    assert _content_to_text(content, dropped=dropped) == "see attachment"
    assert "input_file" in dropped


def test_input_image_not_reported_as_dropped_text() -> None:
    """Images are extracted separately; not a silent readable-text drop."""
    dropped: list[str] = []
    content = [
        {"type": "input_text", "text": "caption"},
        {
            "type": "input_image",
            "image_url": {"url": "data:image/png;base64,xx"},
        },
    ]
    assert _content_to_text(content, dropped=dropped) == "caption"
    assert dropped == []


def test_apply_dropped_content_warning_sets_daari_meta() -> None:
    result = InternalResponse(
        content="ok",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )
    _apply_dropped_content_warning(result, ["input_file"])
    assert result.daari_meta.warning == "dropped_content_parts:input_file"


def test_apply_dropped_content_warning_appends_existing() -> None:
    result = InternalResponse(
        content="ok",
        model="llama3.2:3b",
        daari_meta=DaariMeta(
            tier="L3", executor="ollama", latency_ms=1, warning="budget_warning"
        ),
    )
    _apply_dropped_content_warning(result, ["input_file"])
    assert result.daari_meta.warning == "budget_warning; dropped_content_parts:input_file"

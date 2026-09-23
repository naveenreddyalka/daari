"""Responses-native sampling shapes map onto SamplingParams (#1012)."""

from __future__ import annotations

from daari.gateway.sampling import SamplingParams


SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}


def test_reasoning_effort_from_nested_reasoning():
    params = SamplingParams.from_responses_body(
        {"max_output_tokens": 50, "reasoning": {"effort": "high"}}
    )
    assert params.reasoning_effort == "high"
    assert params.max_tokens == 50


def test_text_format_json_schema_preserves_name_and_strict():
    params = SamplingParams.from_responses_body(
        {
            "text": {
                "format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "answer",
                        "strict": True,
                        "schema": SCHEMA,
                    },
                }
            }
        }
    )
    assert params.json_schema == SCHEMA
    assert params.json_schema_name == "answer"
    assert params.json_schema_strict is True
    assert params.response_format_json is True


def test_text_format_json_object():
    params = SamplingParams.from_responses_body(
        {"text": {"format": {"type": "json_object"}}}
    )
    assert params.response_format_json is True
    assert params.json_schema is None


def test_tool_choice_parallel_and_service_tier():
    params = SamplingParams.from_responses_body(
        {
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "service_tier": "flex",
        }
    )
    assert params.tool_choice == "required"
    assert params.parallel_tool_calls is False
    assert params.service_tier == "flex"


def test_truncation_is_logged(monkeypatch):
    events: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        "daari.gateway.request_log.log_gateway_event",
        lambda event, payload: events.append((event, payload)),
    )
    SamplingParams.from_responses_body({"truncation": "auto"})
    assert any(name == "responses_truncation_ignored" for name, _ in events)

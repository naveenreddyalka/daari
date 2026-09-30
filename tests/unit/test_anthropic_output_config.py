"""Anthropic output_config.effort / format on Messages and L6 replay (#1230 / #1260)."""

from __future__ import annotations

from daari.gateway.anthropic import AnthropicRequest
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import (
    anthropic_headers_for_request,
    to_anthropic_payload,
)


OUTPUT_CONFIG = {"effort": "high"}
OUTPUT_CONFIG_LOW = {"effort": "low"}
OUTPUT_CONFIG_UNKNOWN = {"effort": "turbo"}
_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}
_SCHEMA_ALT = {"type": "object", "properties": {"n": {"type": "integer"}}}
_FORMAT = {"type": "json_schema", "schema": _SCHEMA}
_FORMAT_ALT = {"type": "json_schema", "schema": _SCHEMA_ALT}


class TestHttpRetention:
    def test_anthropic_request_keeps_output_config(self):
        req = AnthropicRequest.model_validate(
            {
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
                "output_config": OUTPUT_CONFIG,
            }
        )
        assert req.output_config == OUTPUT_CONFIG

    def test_from_anthropic_body_maps_effort_without_budget(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 100, "output_config": OUTPUT_CONFIG_LOW}
        )
        assert params.output_config == OUTPUT_CONFIG_LOW
        assert params.reasoning_effort == "low"
        assert params.ollama_think() == "low"

    def test_from_anthropic_body_maps_high_effort(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 100, "output_config": OUTPUT_CONFIG}
        )
        assert params.reasoning_effort == "high"
        assert params.ollama_think() == "high"

    def test_adaptive_thinking_uses_output_config_effort(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 100,
                "thinking": {"type": "adaptive"},
                "output_config": OUTPUT_CONFIG,
            }
        )
        assert params.thinking == {"type": "adaptive"}
        assert params.output_config == OUTPUT_CONFIG
        assert params.reasoning_effort == "high"
        assert params.ollama_think() == "high"

    def test_budget_tokens_wins_over_output_config_effort(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 100,
                "thinking": {"type": "enabled", "budget_tokens": 1024},
                "output_config": OUTPUT_CONFIG,
            }
        )
        assert params.reasoning_effort == "low"
        assert params.ollama_think() == "low"

    def test_unknown_effort_does_not_crash(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 100, "output_config": OUTPUT_CONFIG_UNKNOWN}
        )
        assert params.output_config == OUTPUT_CONFIG_UNKNOWN
        assert params.reasoning_effort == "turbo"
        assert params.ollama_think() is None


class TestPayloadAndBeta:
    def test_to_anthropic_payload_forwards_output_config(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "output_config": OUTPUT_CONFIG}
        )
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
            ),
            model="claude-sonnet-4-0",
        )
        assert payload["output_config"] == OUTPUT_CONFIG

    def test_opus_4_5_adds_effort_beta_when_output_config_present(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "output_config": OUTPUT_CONFIG}
        )
        headers = anthropic_headers_for_request(
            "sk-test",
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
                meta=RequestMeta(),
            ),
            model="claude-opus-4-5-20251101",
        )
        assert "effort-2025-11-24" in headers.get("anthropic-beta", "")

    def test_opus_4_6_does_not_add_effort_beta(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "output_config": OUTPUT_CONFIG}
        )
        headers = anthropic_headers_for_request(
            "sk-test",
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
                meta=RequestMeta(),
            ),
            model="claude-opus-4-6",
        )
        assert "effort-2025-11-24" not in headers.get("anthropic-beta", "")

    def test_effort_beta_not_duplicated_when_already_present(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "output_config": OUTPUT_CONFIG}
        )
        headers = anthropic_headers_for_request(
            "sk-test",
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
                meta=RequestMeta(anthropic_beta="effort-2025-11-24,context-1m-2025-08-07"),
            ),
            model="claude-opus-4-5",
        )
        betas = [b.strip() for b in headers["anthropic-beta"].split(",")]
        assert betas.count("effort-2025-11-24") == 1


class TestOutputConfigFormat:
    def test_format_only_sets_json_schema(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 50,
                "output_config": {"format": _FORMAT},
            }
        )
        assert params.json_schema == _SCHEMA
        assert params.response_format_json is True
        assert params.output_config == {"format": _FORMAT}
        assert params.ollama_format() == _SCHEMA

    def test_effort_and_format_keeps_both(self):
        config = {"effort": "high", "format": _FORMAT}
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "output_config": config}
        )
        assert params.json_schema == _SCHEMA
        assert params.response_format_json is True
        assert params.output_config == config
        assert params.reasoning_effort == "high"
        assert params.ollama_think() == "high"

    def test_legacy_output_format_alone_still_works(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 50,
                "output_format": _FORMAT,
            }
        )
        assert params.json_schema == _SCHEMA
        assert params.response_format_json is True

    def test_output_config_format_preferred_over_legacy(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 50,
                "output_format": _FORMAT_ALT,
                "output_config": {"format": _FORMAT},
            }
        )
        assert params.json_schema == _SCHEMA
        assert params.response_format_json is True

    def test_malformed_output_config_format_is_ignored(self, monkeypatch):
        events: list[str] = []
        monkeypatch.setattr(
            "daari.gateway.request_log.log_gateway_event",
            lambda event, payload: events.append(event),
        )
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 50,
                "output_config": {
                    "format": {"type": "json_schema", "schema": "nope"},
                },
            }
        )
        assert params.json_schema is None
        assert params.response_format_json is False
        assert "json_schema_ignored" in events

    def test_l6_forwards_full_output_config_with_effort_and_format(self):
        config = {"effort": "high", "format": _FORMAT}
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "output_config": config}
        )
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
            ),
            model="claude-sonnet-4-0",
        )
        assert payload["output_config"] == config
        assert payload["output_config"]["format"] == _FORMAT
        assert payload["output_config"]["effort"] == "high"

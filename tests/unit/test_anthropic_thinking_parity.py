"""Anthropic thinking, metadata, and top_k reach L6 payloads (#1009).

Request-level `thinking` / `metadata` were dropped by `AnthropicRequest`;
`top_k` reached local Ollama but not `to_anthropic_payload`.

API version 2026-10-21 removes sampling params (#1849).
"""

from __future__ import annotations

from daari.gateway.anthropic import AnthropicRequest
from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import (
    apply_anthropic_version_sampling_compat,
    to_anthropic_payload,
)
from daari.router.frontier import FrontierExecutor
from daari.router.param_compat import FrontierParamCompatResult


THINKING = {"type": "enabled", "budget_tokens": 4096}
METADATA = {"user_id": "user_abc"}


class TestHttpRetention:
    def test_anthropic_request_temperature_defaults_to_none(self):
        """Omitting temperature must not inject 0.7 (#1849)."""
        req = AnthropicRequest.model_validate(
            {
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
            }
        )
        assert req.temperature is None
        assert req.top_p is None
        assert req.top_k is None

    def test_anthropic_request_keeps_thinking_and_metadata(self):
        req = AnthropicRequest.model_validate(
            {
                "model": "claude-sonnet-4",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 100,
                "thinking": THINKING,
                "metadata": METADATA,
                "top_k": 20,
            }
        )
        assert req.thinking == THINKING
        assert req.metadata == METADATA
        assert req.top_k == 20

    def test_from_anthropic_body_retains_fields(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 100,
                "thinking": THINKING,
                "metadata": METADATA,
                "top_k": 20,
            }
        )
        assert params.thinking == THINKING
        assert params.metadata == METADATA
        assert params.top_k == 20
        # Budget present → reasoning_effort for local think mapping.
        assert params.reasoning_effort == "medium"


class TestPayloadEmission:
    def test_to_anthropic_payload_forwards_thinking_metadata_top_k(self):
        params = SamplingParams.from_anthropic_body(
            {
                "max_tokens": 50,
                "thinking": THINKING,
                "metadata": METADATA,
                "top_k": 15,
            }
        )
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
            ),
            model="claude-sonnet-4-0",
        )
        assert payload["thinking"] == THINKING
        assert payload["metadata"] == METADATA
        assert payload["top_k"] == 15

    def test_thinking_budget_maps_to_ollama_think(self):
        low = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "enabled", "budget_tokens": 1024}}
        )
        high = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "enabled", "budget_tokens": 16000}}
        )
        assert low.ollama_think() == "low"
        assert high.ollama_think() == "high"

    def test_disabled_thinking_does_not_enable_local_think(self):
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "disabled"}}
        )
        assert params.thinking == {"type": "disabled"}
        assert params.ollama_think() is None

    def test_between_tools_degrades_locally_without_silent_drop(self):
        """Local tiers map between_tools → no think and signal the drop (#1828)."""
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 10, "thinking": {"type": "between_tools"}}
        )
        assert params.thinking == {"type": "between_tools"}
        assert params.ollama_think() is None
        assert params.reasoning_effort is None
        assert "thinking.between_tools" in params.dropped_param_names()
        notes = params.unsupported_locally()
        assert any("between_tools" in note for note in notes)

    def test_to_anthropic_payload_forwards_between_tools_unchanged(self):
        """L6 Anthropic path keeps thinking.type=between_tools (#1828)."""
        between = {"type": "between_tools"}
        params = SamplingParams.from_anthropic_body(
            {"max_tokens": 50, "thinking": between}
        )
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                sampling=params,
            ),
            model="claude-sonnet-5-5",
        )
        assert payload["thinking"] == between

    def test_omitted_temperature_not_on_anthropic_payload(self):
        """No default temperature on L6 when the client omitted it (#1849)."""
        payload = to_anthropic_payload(
            InternalRequest(
                messages=[Message(role="user", content="hi")],
                model="daari",
                temperature=None,
            ),
            model="claude-sonnet-4-0",
        )
        assert "temperature" not in payload

    def test_api_version_2026_10_21_strips_sampling_params(self):
        """anthropic-version 2026-10-21 drops temperature/top_p/top_k (#1849)."""
        payload = {
            "model": "claude",
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 50,
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 20,
        }
        dropped = apply_anthropic_version_sampling_compat(payload, "2026-10-21")
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "top_k" not in payload
        assert dropped == ["temperature", "top_p", "top_k"]

    def test_legacy_api_version_keeps_sampling_params(self):
        payload = {
            "model": "claude",
            "temperature": 0.5,
            "top_p": 0.9,
            "top_k": 20,
        }
        dropped = apply_anthropic_version_sampling_compat(payload, "2023-06-01")
        assert payload["temperature"] == 0.5
        assert dropped == []

    def test_frontier_anthropic_payload_records_version_drops(self):
        """Frontier merges API-version sampling drops into last_param_compat (#1849)."""
        executor = FrontierExecutor(
            api_key="sk-ant-test",
            base_url="https://api.anthropic.com",
            default_model="claude-sonnet-4-0",
            provider="anthropic",
        )
        request = InternalRequest(
            messages=[Message(role="user", content="hi")],
            model="daari",
            temperature=0.4,
            sampling=SamplingParams(top_p=0.8, top_k=10, max_tokens=50),
            meta=RequestMeta(anthropic_version="2026-10-21"),
        )
        payload = executor._anthropic_payload(request, stream=False)
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "top_k" not in payload
        compat = executor.last_param_compat
        assert isinstance(compat, FrontierParamCompatResult)
        for name in ("temperature", "top_p", "top_k"):
            assert name in compat.dropped_params

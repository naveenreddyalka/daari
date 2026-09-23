"""Anthropic thinking, metadata, and top_k reach L6 payloads (#1009).

Request-level `thinking` / `metadata` were dropped by `AnthropicRequest`;
`top_k` reached local Ollama but not `to_anthropic_payload`.
"""

from __future__ import annotations

from daari.gateway.anthropic import AnthropicRequest
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.router.anthropic_messages import to_anthropic_payload


THINKING = {"type": "enabled", "budget_tokens": 4096}
METADATA = {"user_id": "user_abc"}


class TestHttpRetention:
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

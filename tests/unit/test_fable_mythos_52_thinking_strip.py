"""Drop Fable/Mythos 5.2 thinking when failover switches to another Claude (#2205)."""

from __future__ import annotations

from daari.gateway.internal import InternalRequest, Message, RequestMeta
from daari.gateway.sampling import SamplingParams
from daari.observability.metrics import Metrics
from daari.router.anthropic_messages import (
    apply_fable_mythos_52_thinking_strip,
    is_fable_mythos_52_model,
    should_strip_fable_mythos_52_thinking,
    to_anthropic_payload,
)
from daari.router.frontier import FrontierExecutor


_THINKING = {
    "type": "thinking",
    "thinking": "52 chain",
    "signature": "sig_52",
}
_REDACTED = {"type": "redacted_thinking", "data": "opaque_52"}


def _request_with_thinking(
    *,
    prior_model: str | None = None,
    blocks: list[dict] | None = None,
) -> InternalRequest:
    meta = RequestMeta()
    if prior_model is not None:
        meta.anthropic_prior_model = prior_model
    return InternalRequest(
        messages=[
            Message(role="user", content="hi"),
            Message(
                role="assistant",
                content="ok",
                thinking_blocks=[dict(b) for b in (blocks or [_THINKING, _REDACTED])],
            ),
            Message(role="user", content="again"),
        ],
        model="daari",
        sampling=SamplingParams(max_tokens=50),
        meta=meta,
    )


class TestIsFableMythos52:
    def test_canonical_and_aliases(self):
        assert is_fable_mythos_52_model("claude-fable-5-2")
        assert is_fable_mythos_52_model("claude-mythos-5-2")
        assert is_fable_mythos_52_model("claude-fable-5-2-20261109")
        assert is_fable_mythos_52_model("anthropic.claude-mythos-5-2")
        assert is_fable_mythos_52_model("claude-fable-5.2")

    def test_non_52_excluded(self):
        assert not is_fable_mythos_52_model("claude-fable-5-1")
        assert not is_fable_mythos_52_model("claude-mythos-5-1")
        assert not is_fable_mythos_52_model("claude-opus-5-5")
        assert not is_fable_mythos_52_model("claude-sonnet-5-5")
        assert not is_fable_mythos_52_model("gpt-6-luna")


class TestShouldStrip:
    def test_52_to_opus(self):
        assert should_strip_fable_mythos_52_thinking(
            from_model="claude-fable-5-2", to_model="claude-opus-5-5"
        )

    def test_52_to_fable_51(self):
        assert should_strip_fable_mythos_52_thinking(
            from_model="claude-mythos-5-2", to_model="claude-fable-5-1"
        )

    def test_onto_52_preserves(self):
        assert not should_strip_fable_mythos_52_thinking(
            from_model="claude-opus-5-5", to_model="claude-fable-5-2"
        )

    def test_within_52_pair_preserves(self):
        assert not should_strip_fable_mythos_52_thinking(
            from_model="claude-fable-5-2", to_model="claude-mythos-5-2"
        )

    def test_same_model_noop(self):
        assert not should_strip_fable_mythos_52_thinking(
            from_model="claude-fable-5-2", to_model="claude-fable-5-2"
        )

    def test_non_anthropic_target_unchanged(self):
        assert not should_strip_fable_mythos_52_thinking(
            from_model="claude-fable-5-2", to_model="gpt-6-luna"
        )


class TestApplyStrip:
    def test_52_to_opus_removes_thinking(self):
        req = _request_with_thinking(prior_model="claude-fable-5-2")
        stripped = apply_fable_mythos_52_thinking_strip(
            req, to_model="claude-opus-5-5"
        )
        assert stripped is True
        assert req.messages[1].thinking_blocks == []
        payload = to_anthropic_payload(req, model="claude-opus-5-5")
        for message in payload["messages"]:
            if message.get("role") != "assistant":
                continue
            content = message.get("content")
            if isinstance(content, list):
                types = [b.get("type") for b in content if isinstance(b, dict)]
                assert "thinking" not in types
                assert "redacted_thinking" not in types
            else:
                assert content == "ok"

    def test_opus_to_52_leaves_thinking(self):
        req = _request_with_thinking(prior_model="claude-opus-5-5")
        stripped = apply_fable_mythos_52_thinking_strip(
            req, to_model="claude-fable-5-2"
        )
        assert stripped is False
        assert len(req.messages[1].thinking_blocks) == 2

    def test_same_model_noop(self):
        req = _request_with_thinking(prior_model="claude-fable-5-2")
        stripped = apply_fable_mythos_52_thinking_strip(
            req, to_model="claude-fable-5-2"
        )
        assert stripped is False
        assert len(req.messages[1].thinking_blocks) == 2

    def test_block_model_field_triggers_strip(self):
        blocks = [
            {**_THINKING, "model": "claude-fable-5-2-20261109"},
            dict(_REDACTED),
        ]
        req = _request_with_thinking(blocks=blocks)
        stripped = apply_fable_mythos_52_thinking_strip(
            req, to_model="claude-opus-5-5"
        )
        assert stripped is True
        assert req.messages[1].thinking_blocks == []

    def test_soft_warning_counter(self):
        metrics = Metrics()
        req = _request_with_thinking(prior_model="claude-mythos-5-2")
        apply_fable_mythos_52_thinking_strip(
            req, to_model="claude-opus-5-5", metrics=metrics
        )
        assert metrics.soft_warnings.get("fable_mythos_52_thinking_stripped") == 1


class TestFrontierPayloadStrip:
    def test_anthropic_payload_strips_on_prior_52(self):
        exe = FrontierExecutor(
            base_url="https://api.anthropic.com",
            api_key="sk-test",
            default_model="claude-opus-5-5",
            provider="anthropic",
        )
        metrics = Metrics()
        exe.metrics = metrics
        req = _request_with_thinking(prior_model="claude-fable-5-2")
        payload = exe._anthropic_payload(req, stream=False)
        assert metrics.soft_warnings.get("fable_mythos_52_thinking_stripped") == 1
        for message in payload["messages"]:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict):
                    assert block.get("type") not in {"thinking", "redacted_thinking"}

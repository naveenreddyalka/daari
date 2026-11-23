"""OpenRouter reasoning object on chat/completions (#2283)."""

from __future__ import annotations

from daari.gateway.internal import DaariMeta, InternalResponse
from daari.gateway.openai import ChatCompletionRequest, build_chat_completion_payload
from daari.gateway.sampling import SamplingParams, apply_reasoning_exclude_to_delta


def test_chat_request_declares_reasoning_object():
    body = ChatCompletionRequest(
        model="daari",
        messages=[{"role": "user", "content": "hi"}],
        reasoning={"effort": "high", "exclude": True},
    )
    assert body.reasoning == {"effort": "high", "exclude": True}


def test_reasoning_effort_maps_from_object():
    params = SamplingParams.from_openai_body({"reasoning": {"effort": "high"}})
    assert params.reasoning_effort == "high"


def test_flat_reasoning_effort_wins_over_object():
    params = SamplingParams.from_openai_body(
        {"reasoning_effort": "low", "reasoning": {"effort": "high"}}
    )
    assert params.reasoning_effort == "low"


def test_enabled_false_maps_to_none_effort():
    params = SamplingParams.from_openai_body({"reasoning": {"enabled": False}})
    assert params.reasoning_effort == "none"


def test_enabled_true_alone_leaves_provider_default():
    params = SamplingParams.from_openai_body({"reasoning": {"enabled": True}})
    assert params.reasoning_effort is None


def test_max_tokens_sets_thinking_budget_and_local_effort():
    params = SamplingParams.from_openai_body({"reasoning": {"max_tokens": 1024}})
    assert params.thinking == {"type": "enabled", "budget_tokens": 1024}
    assert params.reasoning_effort == "low"  # ≤2048 → low


def test_exclude_flag_parsed():
    on = SamplingParams.from_openai_body({"reasoning": {"effort": "medium", "exclude": True}})
    off = SamplingParams.from_openai_body({"reasoning": {"effort": "medium", "exclude": False}})
    assert on.reasoning_exclude is True
    assert off.reasoning_exclude is False


def test_context_and_mode_always_in_dropped_params():
    params = SamplingParams.from_openai_body(
        {"reasoning": {"effort": "high", "context": "foo", "mode": "bar"}}
    )
    dropped = params.dropped_param_names()
    assert "reasoning.context" in dropped
    assert "reasoning.mode" in dropped


def test_exclude_strips_nonstream_reasoning_preserves_usage():
    response = InternalResponse(
        content="answer",
        model="gpt-oss:20b",
        reasoning_content="secret chain",
        daari_meta=DaariMeta(
            tier="L3",
            executor="ollama",
            provider_id="ollama",
            input_tokens=10,
            output_tokens=50,
            usage_estimated=False,
        ),
    )
    kept = build_chat_completion_payload(
        response,
        prompt_chars=40,
        include_daari_meta=True,
        reasoning_exclude=False,
    )
    stripped = build_chat_completion_payload(
        response,
        prompt_chars=40,
        include_daari_meta=True,
        reasoning_exclude=True,
    )
    assert kept["choices"][0]["message"].get("reasoning") == "secret chain"
    assert "reasoning" not in stripped["choices"][0]["message"]
    assert stripped["usage"]["completion_tokens"] == kept["usage"]["completion_tokens"] == 50
    assert stripped["usage"]["prompt_tokens"] == kept["usage"]["prompt_tokens"] == 10


def test_exclude_strips_stream_reasoning_delta():
    delta = {"content": "hi", "reasoning": "think…"}
    assert apply_reasoning_exclude_to_delta(delta, exclude=True) == {"content": "hi"}
    assert apply_reasoning_exclude_to_delta(delta, exclude=False) == delta

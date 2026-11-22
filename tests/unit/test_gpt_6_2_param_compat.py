"""GPT-6.2 Astra/Sol frontier param compat (#2374).

OpenAI GPT-6.2 migration guide: omit temperature/top_p/logprobs, reject
reasoning.effort=none (floor to low), tools require Responses API.
"""

from __future__ import annotations

from unittest.mock import patch

from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import SamplingParams
from daari.router.frontier import FrontierExecutor
from daari.router.param_compat import (
    apply_frontier_param_compat,
    lookup_frontier_param_compat,
)


def _openai_executor(model: str) -> FrontierExecutor:
    return FrontierExecutor(
        base_url="https://api.openai.com/v1",
        default_model=model,
        api_key="sk-test",
        provider="openai",
    )


def _request(
    *,
    temperature: float = 0.9,
    top_p: float | None = 0.8,
    logprobs: bool | None = True,
    reasoning_effort: str | None = None,
    tools: list | None = None,
) -> InternalRequest:
    sampling = SamplingParams(
        top_p=top_p,
        logprobs=logprobs,
        reasoning_effort=reasoning_effort,
    )
    return InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=temperature,
        sampling=sampling,
        tools=tools,
    )


def test_gpt_6_2_table_declares_sampler_strip_floor_and_tools_transport():
    for model in ("gpt-6.2-astra", "gpt-6.2-sol"):
        entry = lookup_frontier_param_compat(model)
        assert entry is not None
        assert entry.unsupported_params == frozenset(
            {"temperature", "top_p", "logprobs"}
        )
        assert entry.unsupported_reasoning_efforts == frozenset({"none"})
        assert entry.reasoning_effort_floor == "low"
        assert entry.tools_transport == "responses"

    astra = lookup_frontier_param_compat("gpt-6.2-astra")
    assert lookup_frontier_param_compat("openai.gpt-6.2-astra-20261117") is astra
    sol = lookup_frontier_param_compat("gpt-6.2-sol")
    assert lookup_frontier_param_compat("openai.gpt-6.2-sol") is sol
    # Must not collapse onto the GPT-6 / 6.1 family entries.
    assert astra is not lookup_frontier_param_compat("gpt-6-astra")
    assert sol is not lookup_frontier_param_compat("gpt-6.1-sol")


def test_gpt_6_2_payload_omits_temperature_top_p_logprobs():
    for model in ("gpt-6.2-astra", "gpt-6.2-sol"):
        executor = _openai_executor(model)
        payload = executor._openai_payload(_request(), stream=False)
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "logprobs" not in payload
        assert payload["model"] == model
        compat = executor.last_param_compat
        assert compat is not None
        for name in ("temperature", "top_p", "logprobs"):
            assert name in compat.dropped_params


def test_gpt_6_2_reasoning_effort_none_floors_to_low():
    for model in ("gpt-6.2-astra", "gpt-6.2-sol"):
        executor = _openai_executor(model)
        payload = executor._openai_payload(
            _request(top_p=None, logprobs=None, reasoning_effort="none"),
            stream=False,
        )
        assert payload["reasoning_effort"] == "low"
        compat = executor.last_param_compat
        assert compat is not None
        assert any("reasoning_effort" in w for w in compat.warnings)
        assert any("low" in w.lower() for w in compat.warnings)


def test_gpt_6_2_tools_warn_toward_responses_api():
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    for model in ("gpt-6.2-astra", "gpt-6.2-sol"):
        executor = _openai_executor(model)
        events: list[tuple[str, dict]] = []

        def capture(event: str, payload: dict) -> None:
            events.append((event, payload))

        with patch("daari.gateway.request_log.log_gateway_event", capture):
            payload = executor._openai_payload(
                _request(top_p=None, logprobs=None, tools=tools),
                stream=False,
            )
        assert payload["tools"] == tools
        compat = executor.last_param_compat
        assert compat is not None
        assert compat.tools_transport_warned is True
        assert any("responses" in w.lower() for w in compat.warnings)
        assert any(name == "frontier.tools_transport" for name, _ in events)


def test_apply_gpt_6_2_compat_strips_and_warns_without_executor():
    for model in ("gpt-6.2-astra", "gpt-6.2-sol"):
        payload = {
            "model": model,
            "temperature": 0.2,
            "top_p": 0.5,
            "logprobs": True,
            "reasoning_effort": "none",
            "tools": [{"type": "function", "function": {"name": "f"}}],
        }
        result = apply_frontier_param_compat(payload, model, has_tools=True)
        assert "temperature" not in payload
        assert "top_p" not in payload
        assert "logprobs" not in payload
        assert payload["reasoning_effort"] == "low"
        assert result.tools_transport_warned is True
        assert any("responses" in w.lower() for w in result.warnings)

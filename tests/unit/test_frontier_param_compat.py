"""Frontier per-model parameter compatibility (#1129).

gpt-6-astra rejects temperature/top_p/logprobs and reasoning_effort=none,
and documents tools as Responses-API-only on chat completions.
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


def _openai_executor(model: str = "gpt-6-astra") -> FrontierExecutor:
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


def test_astra_table_declares_unsupported_params_and_tools_transport():
    entry = lookup_frontier_param_compat("gpt-6-astra")
    assert entry is not None
    assert "temperature" in entry.unsupported_params
    assert "top_p" in entry.unsupported_params
    assert "logprobs" in entry.unsupported_params
    assert "none" in entry.unsupported_reasoning_efforts
    assert entry.reasoning_effort_floor == "minimal"
    assert entry.tools_transport == "responses"
    # Dated / prefixed ids resolve via longest-prefix matching_model_key.
    assert lookup_frontier_param_compat("openai.gpt-6-astra-20260901") is entry


def test_astra_payload_omits_temperature_top_p_logprobs():
    executor = _openai_executor("gpt-6-astra")
    payload = executor._openai_payload(_request(), stream=False)
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "logprobs" not in payload
    assert payload["model"] == "gpt-6-astra"
    assert executor.last_param_compat is not None
    for name in ("temperature", "top_p", "logprobs"):
        assert name in executor.last_param_compat.dropped_params


def test_astra_reasoning_effort_none_floors_to_minimal():
    executor = _openai_executor("gpt-6-astra")
    payload = executor._openai_payload(
        _request(top_p=None, logprobs=None, reasoning_effort="none"),
        stream=False,
    )
    assert payload["reasoning_effort"] == "minimal"
    compat = executor.last_param_compat
    assert compat is not None
    assert any("reasoning_effort" in w for w in compat.warnings)
    assert "reasoning_effort" in compat.dropped_params or any(
        "coerced" in w.lower() or "minimal" in w.lower() for w in compat.warnings
    )


def test_astra_tools_emit_transport_warning_and_event():
    executor = _openai_executor("gpt-6-astra")
    tools = [{"type": "function", "function": {"name": "lookup", "parameters": {}}}]
    events: list[tuple[str, dict]] = []

    def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    with patch("daari.gateway.request_log.log_gateway_event", capture):
        payload = executor._openai_payload(
            _request(top_p=None, logprobs=None, tools=tools),
            stream=False,
        )
    # Honesty only: still present on chat completions; warning + event required.
    assert payload["tools"] == tools
    compat = executor.last_param_compat
    assert compat is not None
    assert compat.tools_transport_warned is True
    assert any("responses" in w.lower() or "tools" in w.lower() for w in compat.warnings)
    assert any(name == "frontier.tools_transport" for name, _ in events)


def test_unknown_and_sol_models_unchanged():
    for model in ("gpt-5.6-sol", "brand-new-frontier-id"):
        assert lookup_frontier_param_compat(model) is None
        executor = _openai_executor(model)
        request = _request(temperature=0.3, top_p=0.5, logprobs=True)
        payload = executor._openai_payload(request, stream=False)
        assert payload["temperature"] == 0.3
        assert payload["top_p"] == 0.5
        assert payload["logprobs"] is True
        compat = executor.last_param_compat
        assert compat is not None
        assert compat.dropped_params == []
        assert compat.warnings == []
        assert compat.tools_transport_warned is False


def test_apply_frontier_param_compat_no_entry_is_noop():
    payload = {"model": "x", "temperature": 0.7, "top_p": 0.9}
    result = apply_frontier_param_compat(payload, "gpt-5.6-sol", has_tools=False)
    assert payload == {"model": "x", "temperature": 0.7, "top_p": 0.9}
    assert result.dropped_params == []
    assert result.warnings == []

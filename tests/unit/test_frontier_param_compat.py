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
    sol = lookup_frontier_param_compat("gpt-6.1-sol")
    assert sol is not None
    assert sol.tools_transport == "responses"
    assert "temperature" in sol.unsupported_params
    assert lookup_frontier_param_compat("openai.gpt-6.1-sol") is sol


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


def test_settings_param_compat_merges_over_builtin():
    """frontier.param_compat overrides merge; builtin astra stays by default (#1173)."""
    from daari.config.settings import Settings
    from daari.router.param_compat import (
        merged_frontier_param_compat_table,
        lookup_frontier_param_compat,
    )

    # Empty override keeps builtin astra.
    default = Settings()
    table = merged_frontier_param_compat_table(default.frontier.param_compat)
    assert lookup_frontier_param_compat("gpt-6-astra", table=table) is not None
    assert "temperature" in lookup_frontier_param_compat("gpt-6-astra", table=table).unsupported_params

    settings = Settings.model_validate(
        {
            "frontier": {
                "param_compat": {
                    "claude-opus-custom": {
                        "unsupported_params": ["temperature", "top_p"],
                    },
                    "gpt-6-astra": {
                        "unsupported_params": ["temperature"],
                        "unsupported_reasoning_efforts": ["none"],
                        "reasoning_effort_floor": "minimal",
                        "tools_transport": "responses",
                    },
                }
            }
        }
    )
    merged = merged_frontier_param_compat_table(settings.frontier.param_compat)
    custom = lookup_frontier_param_compat("claude-opus-custom", table=merged)
    assert custom is not None
    assert custom.unsupported_params == frozenset({"temperature", "top_p"})
    # Operator override replaces the astra entry (narrower strip list).
    astra = lookup_frontier_param_compat("gpt-6-astra", table=merged)
    assert astra is not None
    assert astra.unsupported_params == frozenset({"temperature"})
    assert "top_p" not in astra.unsupported_params


def test_config_validate_accepts_frontier_param_compat(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from daari.cli.app import app as cli_app

    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "frontier:\n"
        "  param_compat:\n"
        "    my-model:\n"
        "      unsupported_params: [temperature]\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(cli_app, ["config", "validate", str(cfg)])
    assert result.exit_code == 0, result.output
    assert "config ok" in result.stdout
    assert "unknown key" not in (result.stdout + result.stderr).lower()


def test_anthropic_egress_applies_param_compat_table():
    """Anthropic stream/non-stream payloads go through the compat strip (#1173)."""
    from daari.router.anthropic_messages import to_anthropic_payload
    from daari.router.param_compat import merged_frontier_param_compat_table

    table = merged_frontier_param_compat_table(
        {
            "claude-test": {
                "unsupported_params": ["temperature", "top_p"],
            }
        }
    )
    executor = FrontierExecutor(
        base_url="https://api.anthropic.com",
        default_model="claude-test",
        api_key="sk-ant",
        provider="anthropic",
        param_compat_table=table,
    )
    request = _request(temperature=0.9, top_p=0.5, logprobs=None)
    payload = to_anthropic_payload(request, model="claude-test", stream=False)
    assert "temperature" in payload
    assert "top_p" in payload
    executor._run_param_compat(payload, has_tools=False)
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert executor.last_param_compat is not None
    assert "temperature" in executor.last_param_compat.dropped_params
    assert "top_p" in executor.last_param_compat.dropped_params


def test_stream_path_attaches_param_compat_to_daari_meta():
    """Stream OpenAI payload sets last_param_compat for daari_meta parity (#1173)."""
    from daari.gateway.internal import DaariMeta

    executor = _openai_executor("gpt-6-astra")
    executor._openai_payload(_request(), stream=True)
    meta = DaariMeta(tier="L6", executor="frontier", provider_id="openai")
    executor._apply_param_compat_meta(meta)
    assert meta.dropped_params is not None
    assert "temperature" in meta.dropped_params
    assert meta.warning is not None
    assert "temperature" in meta.warning

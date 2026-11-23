"""Fable/Mythos 5.1+5.2 frontier param compat (#2384).

Anthropic migration: temperature/top_p/top_k 400 even at defaults; thinking
disabled and budget_tokens 400; forced tool_choice any/tool 400; effort
none floors to low (adaptive cannot be turned off).
"""

from __future__ import annotations

import pytest

from daari.router.param_compat import (
    apply_frontier_param_compat,
    lookup_frontier_param_compat,
)

_FABLE_MYTHOS = (
    "claude-fable-5-1",
    "claude-fable-5-2",
    "claude-mythos-5-2",
)


@pytest.mark.parametrize("model", _FABLE_MYTHOS)
def test_fable_mythos_table_strips_samplers_and_floors_none(model):
    entry = lookup_frontier_param_compat(model)
    assert entry is not None
    assert entry.unsupported_params == frozenset({"temperature", "top_p", "top_k"})
    assert entry.unsupported_reasoning_efforts == frozenset({"none"})
    assert entry.reasoning_effort_floor == "low"


def test_fable_mythos_aliases_match_table():
    fable51 = lookup_frontier_param_compat("claude-fable-5-1")
    assert lookup_frontier_param_compat("anthropic.claude-fable-5-1") is fable51
    assert lookup_frontier_param_compat("claude-fable-5-1-20260901") is fable51
    fable52 = lookup_frontier_param_compat("claude-fable-5-2")
    assert lookup_frontier_param_compat("anthropic.claude-fable-5-2") is fable52
    mythos = lookup_frontier_param_compat("claude-mythos-5-2")
    assert lookup_frontier_param_compat("claude-mythos-5-2-20261109") is mythos


@pytest.mark.parametrize("model", _FABLE_MYTHOS)
def test_default_temperature_one_is_stripped(model):
    """litellm#52341 trap: default temperature=1 must still be omitted."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "temperature": 1,
        "top_p": 1,
        "top_k": 0,
    }
    result = apply_frontier_param_compat(payload, model)
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "top_k" not in payload
    for name in ("temperature", "top_p", "top_k"):
        assert name in result.dropped_params
        assert any(name in w for w in result.warnings)


@pytest.mark.parametrize("model", _FABLE_MYTHOS)
def test_effort_none_floors_to_low_never_emits_disabled(model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "none"},
        "reasoning_effort": "none",
    }
    result = apply_frontier_param_compat(payload, model)
    thinking = payload.get("thinking")
    assert isinstance(thinking, dict)
    assert thinking.get("type") != "disabled"
    assert "budget_tokens" not in thinking
    assert payload.get("reasoning_effort") == "low" or payload.get("output_config", {}).get(
        "effort"
    ) == "low"
    assert any("low" in w.lower() for w in result.warnings)


@pytest.mark.parametrize("model", ("claude-fable-5-2", "claude-mythos-5-2"))
def test_disabled_thinking_remapped_on_52(model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "thinking": {"type": "disabled"},
    }
    result = apply_frontier_param_compat(payload, model)
    assert payload["thinking"] == {"type": "adaptive"}
    assert payload.get("output_config", {}).get("effort") == "low"
    assert any("disabled" in w.lower() or "adaptive" in w.lower() for w in result.warnings)


@pytest.mark.parametrize("model", ("claude-fable-5-2", "claude-mythos-5-2"))
def test_budget_thinking_maps_to_adaptive_effort(model):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "thinking": {"type": "enabled", "budget_tokens": 4096},
    }
    result = apply_frontier_param_compat(payload, model)
    assert payload["thinking"] == {"type": "adaptive"}
    assert "budget_tokens" not in (payload.get("thinking") or {})
    assert payload["output_config"]["effort"] == "medium"
    assert "budget_tokens" in result.dropped_params
    assert any("budget_tokens" in w for w in result.warnings)


@pytest.mark.parametrize("model", _FABLE_MYTHOS)
@pytest.mark.parametrize(
    "tool_choice",
    (
        {"type": "any"},
        {"type": "tool", "name": "lookup"},
    ),
)
def test_forced_tool_choice_degrades_to_auto(model, tool_choice):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "tool_choice": dict(tool_choice),
    }
    result = apply_frontier_param_compat(payload, model)
    assert payload["tool_choice"] == {"type": "auto"}
    assert "tool_choice" in result.dropped_params
    assert any("tool_choice" in w for w in result.warnings)


@pytest.mark.parametrize("model", _FABLE_MYTHOS)
@pytest.mark.parametrize(
    "tool_choice",
    (
        {"type": "auto"},
        {"type": "none"},
        {
            "type": "allowed_tools",
            "mode": "auto",
            "tools": [{"type": "function", "name": "lookup"}],
        },
    ),
)
def test_auto_none_allowed_tools_untouched(model, tool_choice):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "tool_choice": dict(tool_choice),
    }
    apply_frontier_param_compat(payload, model)
    assert payload["tool_choice"] == tool_choice


@pytest.mark.parametrize(
    "model",
    ("claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"),
)
def test_claude_55_none_still_disables_thinking(model):
    """5.5 none→disabled must stay unchanged (#2188 / #2384)."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hi"}],
        "max_tokens": 64,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "none"},
    }
    apply_frontier_param_compat(payload, model)
    assert payload["thinking"] == {"type": "disabled"}


def test_compare_litellm_notes_2026_10_21_sampling_watch():
    from pathlib import Path

    text = Path("docs/developer/resources/compare-litellm.md").read_text(encoding="utf-8")
    assert "2026-10-21" in text
    assert "anthropic-version" in text
    assert "param_compat" in text
    assert "claude-fable-5-2" in text or "Fable/Mythos" in text
    assert "unconditionally" in text

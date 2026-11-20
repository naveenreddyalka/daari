"""tool_choice allowed_tools (nested + flat) across Anthropic / local / cache (#2251)."""

from __future__ import annotations

from daari.cache.exact import cache_key
from daari.gateway.internal import InternalRequest, Message
from daari.gateway.sampling import (
    SamplingParams,
    degrade_allowed_tools_choice,
    filter_tools_by_allowed,
    parse_allowed_tools_choice,
)
from daari.router.anthropic_messages import (
    openai_tool_choice_to_anthropic,
    to_anthropic_payload,
)

LOOKUP = {"type": "function", "function": {"name": "lookup", "parameters": {}}}
SEARCH = {"type": "function", "function": {"name": "search", "parameters": {}}}
WRITE = {"type": "function", "function": {"name": "write", "parameters": {}}}


def _nested(mode: str, names: list[str]) -> dict:
    return {
        "type": "allowed_tools",
        "allowed_tools": {
            "mode": mode,
            "tools": [{"type": "function", "function": {"name": n}} for n in names],
        },
    }


def _flat(mode: str, names: list[str]) -> dict:
    return {
        "type": "allowed_tools",
        "mode": mode,
        "tools": [{"type": "function", "function": {"name": n}} for n in names],
    }


def test_parse_allowed_tools_nested_and_flat():
    nested = parse_allowed_tools_choice(_nested("auto", ["lookup", "search"]))
    assert nested is not None
    assert nested[0] == "auto"
    assert {n for n in nested[1]} == {"lookup", "search"}

    flat = parse_allowed_tools_choice(_flat("required", ["write"]))
    assert flat is not None
    assert flat[0] == "required"
    assert flat[1] == ["write"]

    assert parse_allowed_tools_choice({"type": "function", "function": {"name": "x"}}) is None
    assert parse_allowed_tools_choice("auto") is None


def test_filter_tools_by_allowed_subset():
    tools = [LOOKUP, SEARCH, WRITE]
    filtered = filter_tools_by_allowed(tools, _nested("auto", ["lookup", "write"]))
    assert [t["function"]["name"] for t in filtered] == ["lookup", "write"]


def test_anthropic_maps_allowed_tools_modes():
    assert openai_tool_choice_to_anthropic(_nested("auto", ["lookup"])) == {"type": "auto"}
    assert openai_tool_choice_to_anthropic(_flat("required", ["lookup", "search"])) == {
        "type": "any"
    }
    assert openai_tool_choice_to_anthropic(_flat("required", ["lookup"])) == {
        "type": "tool",
        "name": "lookup",
    }


def test_to_anthropic_payload_filters_tools_and_maps_choice():
    request = InternalRequest(
        messages=[Message(role="user", content="hi")],
        model="claude",
        temperature=0.0,
        tools=[LOOKUP, SEARCH, WRITE],
        sampling=SamplingParams(tool_choice=_nested("required", ["lookup", "search"])),
    )
    payload = to_anthropic_payload(request, model="claude", stream=False)
    names = [t["name"] for t in payload["tools"]]
    assert names == ["lookup", "search"]
    assert payload["tool_choice"] == {"type": "any"}


def test_local_openai_payload_degrades_allowed_tools():
    params = SamplingParams(tool_choice=_flat("required", ["lookup"]))
    local = params.openai_payload(degrade_allowed_tools=True)
    assert local["tool_choice"] == "required"
    frontier = params.openai_payload()
    assert frontier["tool_choice"]["type"] == "allowed_tools"


def test_degrade_allowed_tools_choice_helpers():
    assert degrade_allowed_tools_choice(_nested("auto", ["a"])) == "auto"
    assert degrade_allowed_tools_choice(_flat("required", ["a"])) == "required"


def test_cache_key_splits_on_allowed_subset():
    base = dict(
        messages=[Message(role="user", content="hi")],
        model="daari",
        temperature=0.0,
        tools=[LOOKUP, SEARCH],
    )
    unconstrained = InternalRequest(**base, sampling=SamplingParams())
    constrained = InternalRequest(
        **base, sampling=SamplingParams(tool_choice=_nested("auto", ["lookup"]))
    )
    assert cache_key(unconstrained) != cache_key(constrained)

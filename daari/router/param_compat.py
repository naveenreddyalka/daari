"""Per-model frontier OpenAI parameter compatibility (#1129).

Some frontier ids reject sampler knobs or require a different tool transport.
Lookup uses the same longest-prefix ``matching_model_key`` as pricing/capabilities.
Unknown models are a no-op so behavior stays identical to today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class FrontierParamCompat:
    """Declared constraints for one frontier model id (or prefix)."""

    unsupported_params: frozenset[str] = frozenset()
    unsupported_reasoning_efforts: frozenset[str] = frozenset()
    reasoning_effort_floor: str | None = None
    # When set to "responses", tools on /chat/completions are documented-unsupported.
    tools_transport: str | None = None


@dataclass
class FrontierParamCompatResult:
    dropped_params: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tools_transport_warned: bool = False


# gpt-6-astra: no custom temperature/top_p/logprobs; no reasoning_effort=none;
# tool calling requires the Responses API (chat completions tools unsupported).
_FRONTIER_PARAM_COMPAT: dict[str, FrontierParamCompat] = {
    "gpt-6-astra": FrontierParamCompat(
        unsupported_params=frozenset({"temperature", "top_p", "logprobs"}),
        unsupported_reasoning_efforts=frozenset({"none"}),
        reasoning_effort_floor="minimal",
        tools_transport="responses",
    ),
}


def lookup_frontier_param_compat(model: str) -> FrontierParamCompat | None:
    """Return the compatibility entry for ``model``, or None if unknown."""
    from daari.pricing import matching_model_key

    key = matching_model_key(model, _FRONTIER_PARAM_COMPAT)
    if key is None:
        return None
    return _FRONTIER_PARAM_COMPAT[key]


def apply_frontier_param_compat(
    payload: dict[str, Any],
    model: str,
    *,
    has_tools: bool = False,
) -> FrontierParamCompatResult:
    """Mutate ``payload`` to honor the model's declared constraints.

    Returns dropped param names and human-readable warnings for ``daari_meta``.
    Models with no table entry leave the payload untouched.
    """
    entry = lookup_frontier_param_compat(model)
    result = FrontierParamCompatResult()
    if entry is None:
        return result

    for name in sorted(entry.unsupported_params):
        if name not in payload:
            continue
        del payload[name]
        result.dropped_params.append(name)
        result.warnings.append(
            f"{name} is not supported by {model} and was omitted"
        )

    effort = payload.get("reasoning_effort")
    if (
        isinstance(effort, str)
        and effort.strip().lower() in entry.unsupported_reasoning_efforts
        and entry.reasoning_effort_floor
    ):
        floor = entry.reasoning_effort_floor
        payload["reasoning_effort"] = floor
        if "reasoning_effort" not in result.dropped_params:
            result.dropped_params.append("reasoning_effort")
        result.warnings.append(
            f"reasoning_effort '{effort}' is not supported by {model}; "
            f"coerced to '{floor}'"
        )

    if has_tools and entry.tools_transport == "responses":
        result.tools_transport_warned = True
        result.warnings.append(
            f"tools on /chat/completions are unsupported for {model} "
            f"(requires Responses API)"
        )

    return result

"""Per-model frontier OpenAI parameter compatibility (#1129, #1173).

Some frontier ids reject sampler knobs or require a different tool transport.
Lookup uses the same longest-prefix ``matching_model_key`` as pricing/capabilities.
Unknown models are a no-op so behavior stays identical to today.

``frontier.param_compat`` settings merge over the builtin table so operators can
hotfix provider deprecations without a code release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


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


# gpt-6-astra / gpt-6.1-sol: no custom temperature/top_p/logprobs;
# no reasoning_effort=none; tool calling requires the Responses API
# (chat completions tools unsupported). Same GPT-6 restriction family.
# claude-sonnet-5-5 / claude-opus-5-5: adaptive thinking on by default;
# non-default temperature/top_p/top_k → 400 (strip like gpt-6.1-sol).
_FRONTIER_PARAM_COMPAT: dict[str, FrontierParamCompat] = {
    "gpt-6-astra": FrontierParamCompat(
        unsupported_params=frozenset({"temperature", "top_p", "logprobs"}),
        unsupported_reasoning_efforts=frozenset({"none"}),
        reasoning_effort_floor="minimal",
        tools_transport="responses",
    ),
    "gpt-6.1-sol": FrontierParamCompat(
        unsupported_params=frozenset({"temperature", "top_p", "logprobs"}),
        unsupported_reasoning_efforts=frozenset({"none"}),
        reasoning_effort_floor="minimal",
        tools_transport="responses",
    ),
    "claude-sonnet-5-5": FrontierParamCompat(
        unsupported_params=frozenset({"temperature", "top_p", "top_k"}),
    ),
    "claude-opus-5-5": FrontierParamCompat(
        unsupported_params=frozenset({"temperature", "top_p", "top_k"}),
    ),
}


def compat_from_mapping(raw: Mapping[str, Any] | Any) -> FrontierParamCompat:
    """Build a ``FrontierParamCompat`` from a settings entry or plain mapping."""
    get = raw.get if isinstance(raw, Mapping) else lambda k, d=None: getattr(raw, k, d)
    params = get("unsupported_params") or []
    efforts = get("unsupported_reasoning_efforts") or []
    return FrontierParamCompat(
        unsupported_params=frozenset(str(p) for p in params),
        unsupported_reasoning_efforts=frozenset(str(e).lower() for e in efforts),
        reasoning_effort_floor=(
            str(get("reasoning_effort_floor")).strip()
            if get("reasoning_effort_floor")
            else None
        ),
        tools_transport=(
            str(get("tools_transport")).strip() if get("tools_transport") else None
        ),
    )


def merged_frontier_param_compat_table(
    overrides: Mapping[str, Any] | None = None,
) -> dict[str, FrontierParamCompat]:
    """Builtin table with operator ``frontier.param_compat`` keys merged on top."""
    table = dict(_FRONTIER_PARAM_COMPAT)
    if not overrides:
        return table
    for key, entry in overrides.items():
        if not key:
            continue
        table[str(key)] = compat_from_mapping(entry)
    return table


def lookup_frontier_param_compat(
    model: str,
    *,
    table: Mapping[str, FrontierParamCompat] | None = None,
) -> FrontierParamCompat | None:
    """Return the compatibility entry for ``model``, or None if unknown."""
    from daari.pricing import matching_model_key

    source = table if table is not None else _FRONTIER_PARAM_COMPAT
    key = matching_model_key(model, source)
    if key is None:
        return None
    return source[key]


def apply_frontier_param_compat(
    payload: dict[str, Any],
    model: str,
    *,
    has_tools: bool = False,
    table: Mapping[str, FrontierParamCompat] | None = None,
) -> FrontierParamCompatResult:
    """Mutate ``payload`` to honor the model's declared constraints.

    Returns dropped param names and human-readable warnings for ``daari_meta``.
    Models with no table entry leave the payload untouched.
    """
    entry = lookup_frontier_param_compat(model, table=table)
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

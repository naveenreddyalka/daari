"""Per-model, per-direction token pricing (#157).

Cost used to be one flat `frontier.price_per_1k_tokens` applied to every model
and both directions, so spend and savings could be wrong by an order of
magnitude across a modern model mix. Prices here are USD per 1M tokens, which
is how every provider quotes them.

The shipped table is a convenience, not a contract: list prices change, so
`pricing.models` in config always wins and unknown models fall back to the flat
rate with a `daari doctor` warning.
"""

from __future__ import annotations

from dataclasses import dataclass

# OpenAI / Anthropic / OpenRouter service_tier multipliers (#430).
_SERVICE_TIER_FACTORS = {
    "flex": 0.5,
    "priority": 2.0,
    "standard": 1.0,
    "default": 1.0,
    "auto": 1.0,
}


def service_tier_factor(tier: str | None) -> float:
    """Multiplier for a client `service_tier`. Unknown → 1.0 + event."""
    if tier is None or not str(tier).strip():
        return 1.0
    key = str(tier).strip().lower()
    if key in _SERVICE_TIER_FACTORS:
        return _SERVICE_TIER_FACTORS[key]
    from daari.gateway.request_log import log_gateway_event

    log_gateway_event("service_tier_ignored", {"tier": key})
    return 1.0


@dataclass(frozen=True)
class ResolvedPrice:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None
    is_fallback: bool = False
    input_threshold_tokens: int | None = None


def matching_model_key(model: str, keys: object) -> str | None:
    """Longest configured key that prices or describes `model`.

    Providers append dated suffixes (`claude-fable-5-1-20260901`) and wrap
    ids in a vendor prefix (`anthropic.claude-fable-5-1`, `models/gemini-3.8-flash`).
    A longer key always wins so `gpt-5.6` does not swallow `gpt-5.6-luna`.
    """
    key_list = list(keys)
    if not model or not key_list:
        return None
    matches: list[str] = []
    for candidate in _model_id_candidates(model):
        matches.extend(key for key in key_list if candidate == key or candidate.startswith(key))
    if not matches:
        return None
    return max(matches, key=len)


def _model_id_candidates(model: str) -> list[str]:
    candidates = [model]
    for sep in (".", "/"):
        if sep not in model:
            continue
        tail = model.rsplit(sep, 1)[-1]
        if tail and tail not in candidates:
            candidates.append(tail)
    return candidates


def resolve_price(
    model: str | None,
    pricing: object,
    *,
    fallback_per_1k: float,
    input_tokens: int = 0,
) -> ResolvedPrice:
    """Price for `model`, falling back to the flat per-1k rate when unknown.

    When the model defines ``input_threshold_tokens`` and ``input_tokens``
    reaches that threshold, the above-* rates apply to the whole request (#411).
    """
    table = getattr(pricing, "models", None) or {}
    entry = None
    if model:
        key = matching_model_key(model, table)
        if key is not None:
            entry = table[key]
    if entry is not None:
        input_rate = float(_field(entry, "input_per_1m"))
        output_rate = float(_field(entry, "output_per_1m"))
        cached_rate = _optional_field(entry, "cached_input_per_1m")
        threshold = _optional_int_field(entry, "input_threshold_tokens")
        above_input = _optional_field(entry, "above_input_per_1m")
        above_output = _optional_field(entry, "above_output_per_1m")
        if (
            threshold is not None
            and threshold > 0
            and int(input_tokens) >= threshold
            and above_input is not None
        ):
            if cached_rate is not None and input_rate > 0:
                cached_rate = cached_rate * (above_input / input_rate)
            input_rate = above_input
            if above_output is not None:
                output_rate = above_output
        return ResolvedPrice(
            input_per_1m=input_rate,
            output_per_1m=output_rate,
            cached_input_per_1m=cached_rate,
            is_fallback=False,
            input_threshold_tokens=threshold,
        )
    flat_per_1m = float(fallback_per_1k) * 1000.0
    return ResolvedPrice(
        input_per_1m=flat_per_1m, output_per_1m=flat_per_1m, is_fallback=True
    )


def cost_usd(
    model: str | None,
    input_tokens: int,
    output_tokens: int,
    pricing: object,
    *,
    fallback_per_1k: float,
    cached_input_tokens: int = 0,
    service_tier: str | None = None,
) -> float:
    price = resolve_price(
        model,
        pricing,
        fallback_per_1k=fallback_per_1k,
        input_tokens=input_tokens,
    )
    billable_input = max(0, input_tokens - cached_input_tokens)
    total = billable_input / 1_000_000 * price.input_per_1m
    total += max(0, output_tokens) / 1_000_000 * price.output_per_1m
    if cached_input_tokens and price.cached_input_per_1m is not None:
        total += cached_input_tokens / 1_000_000 * price.cached_input_per_1m
    elif cached_input_tokens:
        total += cached_input_tokens / 1_000_000 * price.input_per_1m
    return total * service_tier_factor(service_tier)


def pricing_warnings(settings: object) -> list[str]:
    """Frontier models that will be costed at the flat fallback rate.

    Surfaced by `daari doctor` so silently-wrong spend reporting is visible
    rather than discovered on a bill.
    """
    frontier = getattr(settings, "frontier", None)
    if frontier is None or not getattr(frontier, "enabled", False):
        return []
    pricing = getattr(settings, "pricing", None)
    fallback = float(getattr(frontier, "price_per_1k_tokens", 0.002))
    models: list[str] = []
    scalar = getattr(frontier, "model", None)
    if scalar:
        models.append(scalar)
    for entry in getattr(frontier, "pool", None) or []:
        name = entry.get("model") if isinstance(entry, dict) else getattr(entry, "model", None)
        if name:
            models.append(name)
    warnings: list[str] = []
    for model in dict.fromkeys(models):
        if resolve_price(model, pricing, fallback_per_1k=fallback).is_fallback:
            warnings.append(
                f"no price configured for frontier model {model!r}; "
                f"costing it at the flat ${fallback}/1k fallback. "
                "Set pricing.models to report real spend."
            )
    return warnings


def _field(entry: object, name: str) -> float:
    if isinstance(entry, dict):
        return entry[name]
    return getattr(entry, name)


def _optional_field(entry: object, name: str) -> float | None:
    value = entry.get(name) if isinstance(entry, dict) else getattr(entry, name, None)
    return float(value) if value is not None else None


def _optional_int_field(entry: object, name: str) -> int | None:
    value = entry.get(name) if isinstance(entry, dict) else getattr(entry, name, None)
    if value is None:
        return None
    return int(value)

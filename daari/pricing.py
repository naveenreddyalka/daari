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


@dataclass(frozen=True)
class ResolvedPrice:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None
    is_fallback: bool = False


def resolve_price(model: str | None, pricing: object, *, fallback_per_1k: float) -> ResolvedPrice:
    """Price for `model`, falling back to the flat per-1k rate when unknown."""
    table = getattr(pricing, "models", None) or {}
    entry = table.get(model) if model else None
    if entry is None and model:
        # Providers append dated or versioned suffixes (gpt-4o-2026-05-13);
        # fall back to the longest configured prefix match.
        matches = [key for key in table if model.startswith(key)]
        if matches:
            entry = table[max(matches, key=len)]
    if entry is not None:
        return ResolvedPrice(
            input_per_1m=float(_field(entry, "input_per_1m")),
            output_per_1m=float(_field(entry, "output_per_1m")),
            cached_input_per_1m=_optional_field(entry, "cached_input_per_1m"),
            is_fallback=False,
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
) -> float:
    price = resolve_price(model, pricing, fallback_per_1k=fallback_per_1k)
    billable_input = max(0, input_tokens - cached_input_tokens)
    total = billable_input / 1_000_000 * price.input_per_1m
    total += max(0, output_tokens) / 1_000_000 * price.output_per_1m
    if cached_input_tokens and price.cached_input_per_1m is not None:
        total += cached_input_tokens / 1_000_000 * price.cached_input_per_1m
    elif cached_input_tokens:
        total += cached_input_tokens / 1_000_000 * price.input_per_1m
    return total


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

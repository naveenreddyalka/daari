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
# `fast` is OpenAI's 30 Jul 2026 rename of Priority (same 2× Standard) (#1527).
# `ultrafast` is 6× Standard for gpt-6.1-sol / gpt-6-astra (#1519).
_SERVICE_TIER_FACTORS = {
    "flex": 0.5,
    "priority": 2.0,
    "fast": 2.0,
    "ultrafast": 6.0,
    "standard": 1.0,
    "default": 1.0,
    "auto": 1.0,
}

# OpenAI Ultrafast is only published for these Responses models (#1519).
_ULTRAFAST_MODELS = ("gpt-6.1-sol", "gpt-6-astra")

# Anthropic fast mode (#1702). Opus 5.5 is GA; Opus 5 / 4.8 still need the beta.
ANTHROPIC_FAST_MODE_BETA = "fast-mode-2026-02-01"
_ANTHROPIC_FAST_GA = "claude-opus-5-5"
_ANTHROPIC_FAST_MODELS = (
    "claude-opus-5-5",
    "claude-opus-5",
    "claude-opus-4.8",
    "claude-opus-4-8",
)
_ANTHROPIC_FAST_PREVIEW = frozenset({"claude-opus-5", "claude-opus-4.8", "claude-opus-4-8"})
# Astra Ultrafast supports US residency + global only; EU pin is unsupported.
_ULTRAFAST_EU_UNSUPPORTED = frozenset({"gpt-6-astra"})

# OpenAI regional processing (data residency) is 1.10× for models released on
# or after 2026-03-05 when a us/eu pin is active (#1531). FedRAMP is out of scope.
_REGIONAL_PROCESSING_FACTOR = 1.10
_REGIONAL_PROCESSING_PINS = frozenset({"us", "eu"})
_REGIONAL_PREMIUM_MODEL_KEYS = (
    "gpt-5.4",
    "gpt-5.5",
    "gpt-5.6",
    "gpt-6",
    "chat-latest",
)


def anthropic_speed_factor(speed: str | None) -> float:
    """2× input and output when the provider reports ``usage.speed == fast`` (#1702)."""
    if speed is None or not str(speed).strip():
        return 1.0
    if str(speed).strip().lower() == "fast":
        return 2.0
    return 1.0


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


def regional_processing_factor(region_pin: str | None, model: str | None) -> float:
    """1.10× when us/eu pin is set on a post-2026-03-05 OpenAI model (#1531)."""
    pin = (region_pin or "").strip().lower()
    if pin not in _REGIONAL_PROCESSING_PINS:
        return 1.0
    if not model or matching_model_key(model, _REGIONAL_PREMIUM_MODEL_KEYS) is None:
        return 1.0
    return _REGIONAL_PROCESSING_FACTOR


@dataclass(frozen=True)
class ServiceTierDecision:
    """Effective service_tier after Ultrafast model/residency gating (#1519)."""

    service_tier: str | None
    warning: str | None = None


def resolve_service_tier_for_request(
    *,
    model: str | None,
    service_tier: str | None,
    region_pin: str | None = None,
) -> ServiceTierDecision:
    """Keep Ultrafast only for supported model + residency; else clear + warn.

    Unsupported model or EU-pinned Astra must not silently bill at 1.0× while
    still advertising ultrafast upstream — clear the tier and set a warning.
    """
    if service_tier is None or not str(service_tier).strip():
        return ServiceTierDecision(service_tier=None)
    key = str(service_tier).strip().lower()
    if key != "ultrafast":
        return ServiceTierDecision(service_tier=key)
    matched = matching_model_key(model or "", _ULTRAFAST_MODELS) if model else None
    if matched is None:
        return ServiceTierDecision(
            service_tier=None, warning="ultrafast_unsupported_model"
        )
    pin = (region_pin or "").strip().lower()
    if pin == "eu" and matched in _ULTRAFAST_EU_UNSUPPORTED:
        return ServiceTierDecision(
            service_tier=None, warning="ultrafast_eu_unsupported"
        )
    return ServiceTierDecision(service_tier="ultrafast")


@dataclass(frozen=True)
class AnthropicSpeedDecision:
    """Effective Anthropic ``speed`` after model and beta gating (#1702)."""

    speed: str | None
    warning: str | None = None


def resolve_anthropic_speed(
    *,
    model: str | None,
    speed: str | None,
    anthropic_beta: str | None = None,
) -> AnthropicSpeedDecision:
    """Forward ``speed: fast`` only when the model publishes fast mode.

    ``claude-opus-5-5`` is GA. ``claude-opus-5`` and ``claude-opus-4.8`` need
    the ``fast-mode-2026-02-01`` beta header. Anything else is cleared so we
    do not advertise a speed the provider will reject.
    """
    if speed is None or not str(speed).strip():
        return AnthropicSpeedDecision(speed=None)
    key = str(speed).strip().lower()
    if key == "standard":
        return AnthropicSpeedDecision(speed="standard")
    if key != "fast":
        return AnthropicSpeedDecision(speed=None, warning="fast_unsupported_speed")
    matched = matching_model_key(model or "", _ANTHROPIC_FAST_MODELS) if model else None
    if matched == _ANTHROPIC_FAST_GA:
        return AnthropicSpeedDecision(speed="fast")
    if matched in _ANTHROPIC_FAST_PREVIEW:
        beta = anthropic_beta or ""
        if ANTHROPIC_FAST_MODE_BETA in beta:
            return AnthropicSpeedDecision(speed="fast")
        return AnthropicSpeedDecision(speed=None, warning="fast_mode_beta_required")
    return AnthropicSpeedDecision(speed=None, warning="fast_unsupported_model")


@dataclass(frozen=True)
class ResolvedPrice:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None
    cache_write_1h_per_1m: float | None = None
    cache_write_per_1m: float | None = None
    is_fallback: bool = False
    input_threshold_tokens: int | None = None


# Decisions API reuses the chat model id but bills input-only (#1484).
# Chat/Responses stay on pricing.models; this overlay must not leak the other way.
_DECISIONS_MODEL_PRICES: dict[str, dict[str, float]] = {
    "gpt-6-luna": {
        "input_per_1m": 0.10,
        "output_per_1m": 0.0,
        "cached_input_per_1m": 0.0,
        "cache_write_per_1m": 0.0,
        "cache_write_1h_per_1m": 0.0,
    },
}


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
    """Id plus vendor-/path-stripped suffixes.

    ``openai.gpt-6.1-sol`` must still see ``gpt-6.1-sol`` — taking only the
    final ``.`` segment yields ``1-sol`` and misses dotted OpenAI ids.
    """
    candidates = [model]
    for sep in (".", "/"):
        if sep not in model:
            continue
        parts = model.split(sep)
        for i in range(1, len(parts)):
            tail = sep.join(parts[i:])
            if tail and tail not in candidates:
                candidates.append(tail)
    return candidates


def resolve_price(
    model: str | None,
    pricing: object,
    *,
    fallback_per_1k: float,
    input_tokens: int = 0,
    billing_path: str | None = None,
) -> ResolvedPrice:
    """Price for `model`, falling back to the flat per-1k rate when unknown.

    When the model defines ``input_threshold_tokens`` and ``input_tokens``
    reaches that threshold, the above-* rates apply to the whole request (#411).

    ``billing_path="decisions"`` uses the Decisions card for ids that OpenAI
    bills differently on ``POST /v1/decisions`` than on Chat/Responses (#1484).
    """
    if (billing_path or "").strip().lower() == "decisions" and model:
        decisions_key = matching_model_key(model, _DECISIONS_MODEL_PRICES)
        if decisions_key is not None:
            return _resolved_from_entry(_DECISIONS_MODEL_PRICES[decisions_key])
    table = getattr(pricing, "models", None) or {}
    entry = None
    if model:
        key = matching_model_key(model, table)
        if key is not None:
            entry = table[key]
    if entry is not None:
        return _resolved_from_entry(entry, input_tokens=input_tokens)
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
    cache_write_tokens: int = 0,
    cache_ttl: str | None = None,
    service_tier: str | None = None,
    region_pin: str | None = None,
    billing_path: str | None = None,
    usage_speed: str | None = None,
) -> float:
    price = resolve_price(
        model,
        pricing,
        fallback_per_1k=fallback_per_1k,
        input_tokens=input_tokens,
        billing_path=billing_path,
    )
    write_tokens = max(0, int(cache_write_tokens))
    billable_input = max(0, input_tokens - cached_input_tokens)
    total = billable_input / 1_000_000 * price.input_per_1m
    total += max(0, output_tokens) / 1_000_000 * price.output_per_1m
    if cached_input_tokens and price.cached_input_per_1m is not None:
        total += cached_input_tokens / 1_000_000 * price.cached_input_per_1m
    elif cached_input_tokens:
        total += cached_input_tokens / 1_000_000 * price.input_per_1m
    if write_tokens:
        total += write_tokens / 1_000_000 * _cache_write_rate(price, cache_ttl)
    return (
        total
        * service_tier_factor(service_tier)
        * regional_processing_factor(region_pin, model)
        * anthropic_speed_factor(usage_speed)
    )


def _cache_write_rate(price: ResolvedPrice, cache_ttl: str | None) -> float:
    """1h TTL uses cache_write_1h_per_1m; missing/5m keeps today's input rate.

    ``cache_write_per_1m`` (including 0) overrides the non-1h write rate so a
    path can bill cache writes at $0 without changing chat models.
    """
    ttl = (cache_ttl or "").strip().lower()
    if ttl in {"1h", "1hr", "60m"}:
        if price.cache_write_1h_per_1m is not None:
            return float(price.cache_write_1h_per_1m)
        # Configured models should set the field; fall back to 2× input.
        return float(price.input_per_1m) * 2.0
    if price.cache_write_per_1m is not None:
        return float(price.cache_write_per_1m)
    return float(price.input_per_1m)


def _resolved_from_entry(entry: object, *, input_tokens: int = 0) -> ResolvedPrice:
    input_rate = float(_field(entry, "input_per_1m"))
    output_rate = float(_field(entry, "output_per_1m"))
    cached_rate = _optional_field(entry, "cached_input_per_1m")
    write_1h = _optional_field(entry, "cache_write_1h_per_1m")
    write_rate = _optional_field(entry, "cache_write_per_1m")
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
        if write_1h is not None and input_rate > 0:
            write_1h = write_1h * (above_input / input_rate)
        if write_rate is not None and input_rate > 0:
            write_rate = write_rate * (above_input / input_rate)
        input_rate = above_input
        if above_output is not None:
            output_rate = above_output
    return ResolvedPrice(
        input_per_1m=input_rate,
        output_per_1m=output_rate,
        cached_input_per_1m=cached_rate,
        cache_write_1h_per_1m=write_1h,
        cache_write_per_1m=write_rate,
        is_fallback=False,
        input_threshold_tokens=threshold,
    )


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

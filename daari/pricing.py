"""Per-model, per-direction token pricing (#157).

Cost used to be one flat `frontier.price_per_1k_tokens` applied to every model
and both directions, so spend and savings could be wrong by an order of
magnitude across a modern model mix. Prices here are USD per 1M tokens, which
is how every provider quotes them.

The shipped table is a convenience, not a contract: list prices change, so
`pricing.models` in config always wins and unknown models fall back to the flat
rate with a `daari doctor` warning. An entry may set ``alias_of`` /
``pricing_provider`` to inherit rates from another catalog key (#2005); explicit
rate fields on that entry still override the aliased values.
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


def anthropic_fast_mode_spec(model: str | None) -> dict[str, bool] | None:
    """Fast-mode catalog flags, or None when the id does not publish fast mode.

    ``beta_header`` is true for Opus 5 / 4.8 (need ``fast-mode-2026-02-01``)
    and false for Opus 5.5, which is GA (#1740).
    """
    matched = matching_model_key(model or "", _ANTHROPIC_FAST_MODELS) if model else None
    if matched is None:
        return None
    return {"supported": True, "beta_header": matched in _ANTHROPIC_FAST_PREVIEW}


@dataclass(frozen=True)
class ResolvedPrice:
    input_per_1m: float
    output_per_1m: float
    cached_input_per_1m: float | None = None
    cache_write_1h_per_1m: float | None = None
    cache_write_30m_per_1m: float | None = None
    cache_write_12h_per_1m: float | None = None
    cache_write_per_1m: float | None = None
    is_fallback: bool = False
    input_threshold_tokens: int | None = None


# Decisions API reuses the chat model id but bills input-only (#1484 / #1886).
# GA prompt-cache discounts: cached reads at $0.01/1M; output stays $0.
# Chat/Responses stay on pricing.models; this overlay must not leak the other way.
_DECISIONS_MODEL_PRICES: dict[str, dict[str, float]] = {
    "gpt-6-luna": {
        "input_per_1m": 0.10,
        "output_per_1m": 0.0,
        "cached_input_per_1m": 0.01,
        "cache_write_per_1m": 0.0,
        "cache_write_1h_per_1m": 0.0,
    },
}


def is_ollama_cloud_model(model: str | None) -> bool:
    """True for Ollama cloud ids such as ``clef:cloud`` (billed on ollama.com)."""
    return (model or "").strip().endswith(":cloud")


def apply_cloud_billing_warning(
    meta: object,
    pricing: object,
    *,
    fallback_per_1k: float,
    model: str | None = None,
) -> None:
    """Warn on ``daari_meta`` when a served ``:cloud`` id has no configured price.

    Priced cloud models stay silent. Unpriced ones use the flat fallback in the
    ledger, and the warning says so instead of leaving spend at a quiet $0.
    """
    name = (model or getattr(meta, "model", None) or "").strip()
    if not is_ollama_cloud_model(name):
        return
    if not resolve_price(name, pricing, fallback_per_1k=fallback_per_1k).is_fallback:
        return
    note = (
        f"no price configured for Ollama cloud model {name!r}; "
        f"costing it at the flat ${float(fallback_per_1k)}/1k fallback. "
        "Set pricing.models to report real spend."
    )
    existing = getattr(meta, "warning", None)
    meta.warning = f"{existing}; {note}" if existing else note


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
    matched_key: str | None = None
    if model:
        matched_key = matching_model_key(model, table)
        if matched_key is not None:
            entry = table[matched_key]
    if entry is not None:
        resolved = _resolved_from_entry(
            entry,
            input_tokens=input_tokens,
            table=table,
            exclude_keys={matched_key} if matched_key else set(),
        )
        if resolved is not None:
            return resolved
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
    """TTL-keyed write rates; missing/5m keeps today's input (or cache_write_per_1m).

    OpenAI Responses ``30m`` / ``12h`` use ``cache_write_30m_per_1m`` /
    ``cache_write_12h_per_1m`` (1.25× / 2.5× input totals) (#1843). Anthropic
    ``1h`` uses ``cache_write_1h_per_1m``. ``cache_write_per_1m`` (including 0)
    overrides the non-TTL write rate so a path can bill writes at $0.
    """
    ttl = (cache_ttl or "").strip().lower()
    if ttl in {"12h", "12hr"}:
        if price.cache_write_12h_per_1m is not None:
            return float(price.cache_write_12h_per_1m)
        return float(price.input_per_1m) * 2.5
    if ttl in {"30m", "30min"}:
        if price.cache_write_30m_per_1m is not None:
            return float(price.cache_write_30m_per_1m)
        return float(price.input_per_1m) * 1.25
    if ttl in {"1h", "1hr", "60m"}:
        if price.cache_write_1h_per_1m is not None:
            return float(price.cache_write_1h_per_1m)
        # Configured models should set the field; fall back to 2× input.
        return float(price.input_per_1m) * 2.0
    if price.cache_write_per_1m is not None:
        return float(price.cache_write_per_1m)
    return float(price.input_per_1m)


_RATE_FIELDS = (
    "input_per_1m",
    "output_per_1m",
    "cached_input_per_1m",
    "cache_write_1h_per_1m",
    "cache_write_30m_per_1m",
    "cache_write_12h_per_1m",
    "cache_write_per_1m",
    "input_threshold_tokens",
    "above_input_per_1m",
    "above_output_per_1m",
)


def _alias_target(entry: object) -> str | None:
    """``alias_of`` wins over ``pricing_provider`` when both are set."""
    for name in ("alias_of", "pricing_provider"):
        raw = entry.get(name) if isinstance(entry, dict) else getattr(entry, name, None)
        if raw is None:
            continue
        text = str(raw).strip()
        if text:
            return text
    return None


def _entry_rate_dict(entry: object) -> dict[str, float | int]:
    """Copy configured rate fields; omit unset / alias-only Nones."""
    out: dict[str, float | int] = {}
    for name in _RATE_FIELDS:
        if name == "input_threshold_tokens":
            value = _optional_int_field(entry, name)
        else:
            value = _optional_field(entry, name)
        if value is not None:
            out[name] = value
    return out


def _merged_rate_entry(
    entry: object,
    *,
    table: object | None,
    exclude_keys: set[str],
) -> dict[str, float | int] | None:
    """Alias chain + explicit overrides → one rate dict (no threshold applied)."""
    merged: dict[str, float | int] = {}
    alias = _alias_target(entry)
    if alias and table is not None:
        candidates = [k for k in list(table) if k not in exclude_keys]
        target_key = matching_model_key(alias, candidates)
        if target_key is not None:
            parent = _merged_rate_entry(
                table[target_key],
                table=table,
                exclude_keys=exclude_keys | {target_key},
            )
            if parent is not None:
                merged.update(parent)
    merged.update(_entry_rate_dict(entry))
    if "input_per_1m" not in merged or "output_per_1m" not in merged:
        return None
    return merged


def _resolved_from_entry(
    entry: object,
    *,
    input_tokens: int = 0,
    table: object | None = None,
    exclude_keys: set[str] | None = None,
) -> ResolvedPrice | None:
    """Resolve rates, following ``alias_of`` / ``pricing_provider`` when present.

    Returns None when an alias cannot be resolved and the entry has no
    explicit input/output rates (caller falls back to the flat rate).
    """
    merged = _merged_rate_entry(
        entry, table=table, exclude_keys=set(exclude_keys or ())
    )
    if merged is None:
        return None

    input_rate = float(merged["input_per_1m"])
    output_rate = float(merged["output_per_1m"])
    cached_rate = (
        float(merged["cached_input_per_1m"]) if "cached_input_per_1m" in merged else None
    )
    write_1h = (
        float(merged["cache_write_1h_per_1m"])
        if "cache_write_1h_per_1m" in merged
        else None
    )
    write_30m = (
        float(merged["cache_write_30m_per_1m"])
        if "cache_write_30m_per_1m" in merged
        else None
    )
    write_12h = (
        float(merged["cache_write_12h_per_1m"])
        if "cache_write_12h_per_1m" in merged
        else None
    )
    write_rate = (
        float(merged["cache_write_per_1m"]) if "cache_write_per_1m" in merged else None
    )
    threshold = (
        int(merged["input_threshold_tokens"])
        if "input_threshold_tokens" in merged
        else None
    )
    above_input = (
        float(merged["above_input_per_1m"]) if "above_input_per_1m" in merged else None
    )
    above_output = (
        float(merged["above_output_per_1m"]) if "above_output_per_1m" in merged else None
    )
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
        if write_30m is not None and input_rate > 0:
            write_30m = write_30m * (above_input / input_rate)
        if write_12h is not None and input_rate > 0:
            write_12h = write_12h * (above_input / input_rate)
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
        cache_write_30m_per_1m=write_30m,
        cache_write_12h_per_1m=write_12h,
        cache_write_per_1m=write_rate,
        is_fallback=False,
        input_threshold_tokens=threshold,
    )


def _configured_model_ids(settings: object) -> list[str]:
    """Model ids an operator pointed at a local or org executor."""
    found: list[str] = []

    def add(value: object) -> None:
        if isinstance(value, str) and value.strip():
            found.append(value.strip())

    models = getattr(settings, "models", None)
    for name in ("l3", "l4", "l5"):
        add(getattr(models, name, None) if models is not None else None)
    decisions = getattr(settings, "decisions", None)
    for value in getattr(decisions, "local_models", None) or []:
        add(value)
    routing = getattr(settings, "routing", None)
    org = getattr(routing, "org_pool", None) if routing is not None else None
    add(getattr(org, "model", None) if org is not None else None)
    pool = getattr(routing, "local_pool", None) if routing is not None else None
    for backend in getattr(pool, "backends", None) or []:
        if isinstance(backend, dict):
            add(backend.get("model"))
        else:
            add(getattr(backend, "model", None))
    classifier = getattr(routing, "decision_classifier", None) if routing is not None else None
    add(getattr(classifier, "model", None) if classifier is not None else None)
    mlx = getattr(settings, "mlx", None)
    for value in (getattr(mlx, "models", None) or {}).values():
        add(value)
    return found


def pricing_warnings(settings: object) -> list[str]:
    """Models that will be costed at the flat fallback rate.

    Surfaced by `daari doctor` so silently-wrong spend reporting is visible
    rather than discovered on a bill. Frontier warnings require
    ``frontier.enabled``. Ollama ``:cloud`` ids are billed on the operator's
    Ollama account even when frontier is off, so those warn whenever a
    configured tier or pool model ends with ``:cloud`` and has no price.
    """
    frontier = getattr(settings, "frontier", None)
    pricing = getattr(settings, "pricing", None)
    fallback = 0.002
    if frontier is not None:
        fallback = float(getattr(frontier, "price_per_1k_tokens", 0.002) or 0.002)
    warnings: list[str] = []
    frontier_models: list[str] = []
    if frontier is not None and getattr(frontier, "enabled", False):
        scalar = getattr(frontier, "model", None)
        if scalar:
            frontier_models.append(scalar)
        for entry in getattr(frontier, "pool", None) or []:
            name = entry.get("model") if isinstance(entry, dict) else getattr(entry, "model", None)
            if name:
                frontier_models.append(name)
    for model in dict.fromkeys(frontier_models):
        if resolve_price(model, pricing, fallback_per_1k=fallback).is_fallback:
            warnings.append(
                f"no price configured for frontier model {model!r}; "
                f"costing it at the flat ${fallback}/1k fallback. "
                "Set pricing.models to report real spend."
            )
    cloud_models = [
        model for model in _configured_model_ids(settings) if is_ollama_cloud_model(model)
    ]
    for model in dict.fromkeys(cloud_models):
        if resolve_price(model, pricing, fallback_per_1k=fallback).is_fallback:
            warnings.append(
                f"no price configured for Ollama cloud model {model!r}; "
                f"costing it at the flat ${fallback}/1k fallback. "
                "Set pricing.models to report real spend."
            )
    table = getattr(pricing, "models", None) or {}
    for key, entry in table.items():
        alias = _alias_target(entry)
        if not alias:
            continue
        candidates = [k for k in table if k != key]
        if matching_model_key(alias, candidates) is None:
            warnings.append(
                f"pricing.models[{key!r}] alias_of/pricing_provider {alias!r} "
                "is unknown; costing it at the flat fallback unless this entry "
                "sets explicit rates. Set alias_of to a shipped or configured key."
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

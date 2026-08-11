"""Validation for runtime config patches (issue #137 review).

The config editor and org policy sync both write into a live `Settings` tree.
Pydantic models here are built without `validate_assignment`, so `setattr` on a
loaded Settings bypasses field validation — a bad value survives until the next
request path touches it. These helpers validate and range-check first so callers
can reject a patch instead of half-applying it.
"""

from __future__ import annotations

from typing import Any

from daari.config.settings import BoundariesSettings

PREFER_CHOICES = ("latency", "accuracy", "balanced", "cost")
TIER_CHOICES = ("L3", "L4", "L5")
BOUNDARY_MODES = ("off", "warn", "block")


class ConfigValidationError(ValueError):
    """A patch value is malformed or out of range."""


def _number(value: Any, key: str, *, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ConfigValidationError(f"{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigValidationError(f"{key} must be a number") from exc
    if number != number or not (low <= number <= high):
        raise ConfigValidationError(f"{key} must be between {low} and {high}")
    return number


def validated_routing(patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "confidence_threshold" in patch:
        out["confidence_threshold"] = _number(
            patch["confidence_threshold"], "confidence_threshold", low=0.0, high=1.0
        )
    if "latency_budget_ms" in patch:
        out["latency_budget_ms"] = int(
            _number(patch["latency_budget_ms"], "latency_budget_ms", low=0, high=600_000)
        )
    if "prefer" in patch:
        prefer = str(patch["prefer"]).strip()
        if prefer not in PREFER_CHOICES:
            raise ConfigValidationError(f"prefer must be one of {PREFER_CHOICES}")
        out["prefer"] = prefer
    if "max_tier_for_chat" in patch:
        tier = patch["max_tier_for_chat"]
        if tier is None or (isinstance(tier, str) and not tier.strip()):
            out["max_tier_for_chat"] = None
        else:
            tier = str(tier).strip().upper()
            if tier not in TIER_CHOICES:
                raise ConfigValidationError(
                    f"max_tier_for_chat must be one of {TIER_CHOICES} or null"
                )
            out["max_tier_for_chat"] = tier
    return out


def validated_frontier(patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("daily_budget_usd", "monthly_budget_usd"):
        if key in patch:
            out[key] = _number(patch[key], key, low=0.0, high=1_000_000.0)
    if "soft_budget_ratio" in patch:
        out["soft_budget_ratio"] = _number(
            patch["soft_budget_ratio"], "soft_budget_ratio", low=0.0, high=1.0
        )
    return out


def validated_cache(patch: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in ("l0_ttl_seconds", "l1_ttl_seconds"):
        if key in patch:
            out[key] = _number(patch[key], key, low=0.0, high=31_536_000.0)
    if "l1_similarity_threshold" in patch:
        out["l1_similarity_threshold"] = _number(
            patch["l1_similarity_threshold"], "l1_similarity_threshold", low=0.0, high=1.0
        )
    return out


def merged_boundaries(
    current: BoundariesSettings, patch: dict[str, Any]
) -> BoundariesSettings:
    """Validate a boundaries patch against the model instead of raw setattr."""
    unknown = sorted(set(patch) - set(BoundariesSettings.model_fields))
    if unknown:
        raise ConfigValidationError(f"unknown boundaries keys: {unknown}")
    mode = patch.get("mode")
    if mode is not None and str(mode) not in BOUNDARY_MODES:
        raise ConfigValidationError(f"mode must be one of {BOUNDARY_MODES}")
    for key in ("clear_out_threshold", "clear_in_threshold"):
        if key in patch:
            _number(patch[key], key, low=0.0, high=1.0)
    merged = current.model_dump()
    merged.update(patch)
    try:
        return BoundariesSettings.model_validate(merged)
    except Exception as exc:
        raise ConfigValidationError(f"invalid boundaries patch: {exc}") from exc

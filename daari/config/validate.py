"""Validation for runtime config patches (issue #137 review).

The config editor and org policy sync both write into a live `Settings` tree.
Runtime settings models now use `validate_assignment`, so a bad `setattr` raises
`ValidationError`. These helpers still validate first and translate failures
into `ConfigValidationError` so HTTP callers stay on 400, not 500.
"""

from __future__ import annotations

import logging
import os
from types import UnionType
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

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


def _bool(value: Any, key: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigValidationError(f"{key} must be a bool")
    return value


def validated_decision_classifier(patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise ConfigValidationError("decision_classifier must be an object")
    allowed = {"enabled", "model", "timeout_seconds", "agent_turns"}
    unknown = sorted(set(patch) - allowed)
    if unknown:
        raise ConfigValidationError(f"unknown decision_classifier keys: {unknown}")
    out: dict[str, Any] = {}
    if "enabled" in patch:
        out["enabled"] = _bool(patch["enabled"], "decision_classifier.enabled")
    if "model" in patch:
        model = str(patch["model"]).strip()
        if not model:
            raise ConfigValidationError("decision_classifier.model must be a non-empty string")
        out["model"] = model
    if "timeout_seconds" in patch:
        out["timeout_seconds"] = _number(
            patch["timeout_seconds"],
            "decision_classifier.timeout_seconds",
            low=0.1,
            high=600.0,
        )
    if "agent_turns" in patch:
        out["agent_turns"] = _bool(patch["agent_turns"], "decision_classifier.agent_turns")
    return out


def validated_integrations(patch: dict[str, Any]) -> dict[str, Any]:
    """Safe MCP ownership leaves only — secrets stay non-editable (#1322)."""
    if not isinstance(patch, dict):
        raise ConfigValidationError("integrations must be an object")
    allowed_top = {"mcp_oauth", "mcp_aggregate_egress", "mcp_registry"}
    unknown_top = sorted(set(patch) - allowed_top)
    if unknown_top:
        raise ConfigValidationError(f"unknown integrations keys: {unknown_top}")
    out: dict[str, Any] = {}
    if "mcp_oauth" in patch:
        oauth = patch["mcp_oauth"]
        if not isinstance(oauth, dict):
            raise ConfigValidationError("mcp_oauth must be an object")
        secret_keys = sorted(
            k for k in oauth if k in {"signing_secret", "client_secret", "client_secrets"}
        )
        if secret_keys:
            raise ConfigValidationError(
                f"mcp_oauth secrets are not editable via the config editor: {secret_keys}"
            )
        allowed_oauth = {"local_as", "protected_resource"}
        unknown_oauth = sorted(set(oauth) - allowed_oauth)
        if unknown_oauth:
            raise ConfigValidationError(f"unknown mcp_oauth keys: {unknown_oauth}")
        oauth_out: dict[str, Any] = {}
        for key in ("local_as", "protected_resource"):
            if key in oauth:
                oauth_out[key] = _bool(oauth[key], f"mcp_oauth.{key}")
        if oauth_out:
            out["mcp_oauth"] = oauth_out
    if "mcp_aggregate_egress" in patch:
        agg = patch["mcp_aggregate_egress"]
        if not isinstance(agg, dict):
            raise ConfigValidationError("mcp_aggregate_egress must be an object")
        unknown_agg = sorted(set(agg) - {"enabled"})
        if unknown_agg:
            raise ConfigValidationError(f"unknown mcp_aggregate_egress keys: {unknown_agg}")
        agg_out: dict[str, Any] = {}
        if "enabled" in agg:
            agg_out["enabled"] = _bool(agg["enabled"], "mcp_aggregate_egress.enabled")
        if agg_out:
            out["mcp_aggregate_egress"] = agg_out
    if "mcp_registry" in patch:
        reg = patch["mcp_registry"]
        if not isinstance(reg, dict):
            raise ConfigValidationError("mcp_registry must be an object")
        unknown_reg = sorted(set(reg) - {"enabled"})
        if unknown_reg:
            raise ConfigValidationError(f"unknown mcp_registry keys: {unknown_reg}")
        reg_out: dict[str, Any] = {}
        if "enabled" in reg:
            reg_out["enabled"] = _bool(reg["enabled"], "mcp_registry.enabled")
        if reg_out:
            out["mcp_registry"] = reg_out
    return out


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
    if "decision_classifier" in patch:
        classifier = validated_decision_classifier(patch["decision_classifier"] or {})
        if classifier:
            out["decision_classifier"] = classifier
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


logger = logging.getLogger("daari.config")

_MISSING = object()


def strict_config_enabled(flag: bool | None = None) -> bool:
    """True when `--strict` or `DAARI_STRICT_CONFIG=1` is set."""
    if flag:
        return True
    raw = os.environ.get("DAARI_STRICT_CONFIG", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _unwrap(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin in (UnionType,) or str(origin) == "typing.Union":
        args = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(args) == 1:
            return _unwrap(args[0])
    return annotation


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def unknown_config_keys(data: Any, model: type[BaseModel], prefix: str = "") -> list[str]:
    """Dotted paths present in `data` but absent from `model` (nested included)."""
    if not isinstance(data, dict):
        return []
    found: list[str] = []
    fields = model.model_fields
    for key, value in data.items():
        path = f"{prefix}{key}"
        if key not in fields:
            found.append(path)
            continue
        annotation = _unwrap(fields[key].annotation)
        origin = get_origin(annotation)
        if _is_model(annotation):
            found.extend(unknown_config_keys(value, annotation, prefix=f"{path}."))
            continue
        if origin is dict and isinstance(value, dict):
            args = get_args(annotation)
            value_type = _unwrap(args[1]) if len(args) == 2 else None
            if _is_model(value_type):
                for subkey, subval in value.items():
                    found.extend(
                        unknown_config_keys(subval, value_type, prefix=f"{path}.{subkey}.")
                    )
            continue
        if origin is list and isinstance(value, list):
            args = get_args(annotation)
            item_type = _unwrap(args[0]) if args else None
            if _is_model(item_type):
                for index, item in enumerate(value):
                    found.extend(
                        unknown_config_keys(item, item_type, prefix=f"{path}.{index}.")
                    )
    return found


def strict_unknown_error(keys: list[str]) -> ValidationError:
    return ValidationError.from_exception_data(
        "Settings",
        [
            {
                "type": "extra_forbidden",
                "loc": tuple(key.split(".")),
                "input": None,
            }
            for key in keys
        ],
    )


def apply_unknown_key_policy(keys: list[str], *, strict: bool | None = None) -> None:
    """Warn by default; raise when strict mode is on. Never prints."""
    if not keys:
        return
    if strict_config_enabled(strict):
        raise strict_unknown_error(keys)
    logger.warning("unknown config keys: %s", ", ".join(keys))


def asr_frontier_fallback_findings(settings: Any) -> list[str]:
    """Cross-check ``asr.frontier_fallback`` against frontier wiring (#817)."""
    asr = getattr(settings, "asr", None)
    if asr is None or not bool(getattr(asr, "frontier_fallback", False)):
        return []
    frontier = getattr(settings, "frontier", None)
    if frontier is None or not bool(getattr(frontier, "enabled", False)):
        return ["asr.frontier_fallback is true but frontier.enabled is false"]
    base = str(getattr(asr, "base_url", "") or "").strip()
    if base:
        return []
    # Empty base_url: fallback is the only ASR path — mirror doctor.
    try:
        from daari.gateway.transcriptions import resolve_asr_target

        target = resolve_asr_target(settings)
    except Exception:  # noqa: BLE001 — validate must stay side-effect light
        target = None
    if target is None or not getattr(target, "api_key", None):
        return ["asr.frontier_fallback is true but no frontier API key resolves"]
    return []


def local_pool_frontier_fallback_findings(settings: Any) -> list[str]:
    """Cross-check ``routing.local_pool.frontier_fallback`` (#846)."""
    pool = getattr(getattr(settings, "routing", None), "local_pool", None)
    if pool is None or not bool(getattr(pool, "frontier_fallback", False)):
        return []
    frontier = getattr(settings, "frontier", None)
    if frontier is None or not bool(getattr(frontier, "enabled", False)):
        return [
            "routing.local_pool.frontier_fallback is true but frontier.enabled is false"
        ]
    return []


def config_findings(user: dict[str, Any], merged: dict[str, Any], model: type[BaseModel]) -> list[str]:
    """Unknown keys plus type / range errors. Used by `daari config validate`."""
    findings = [f"unknown key: {key}" for key in unknown_config_keys(user, model)]
    settings: BaseModel | None = None
    try:
        settings = model.model_validate(merged)
    except ValidationError as exc:
        known = {item.removeprefix("unknown key: ") for item in findings}
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            if err.get("type") == "extra_forbidden":
                label = f"unknown key: {loc}" if loc else "unknown key"
                if loc not in known and label not in findings:
                    findings.append(label)
                continue
            where = loc or "<root>"
            findings.append(f"{where}: {err.get('msg', 'invalid')}")
    if settings is not None:
        findings.extend(asr_frontier_fallback_findings(settings))
        findings.extend(local_pool_frontier_fallback_findings(settings))
    return findings

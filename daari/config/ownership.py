"""Live-vs-file ownership metadata for GET/PATCH /v1/daari/config (#1111)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_SAFE_SECTIONS = ("routing", "frontier", "cache", "boundaries")

# Flat leaf paths exposed by the config editor GET payload.
_FIELD_PATHS: tuple[tuple[str, ...], ...] = (
    ("routing", "prefer"),
    ("routing", "confidence_threshold"),
    ("routing", "latency_budget_ms"),
    ("routing", "max_tier_for_chat"),
    ("frontier", "daily_budget_usd"),
    ("frontier", "monthly_budget_usd"),
    ("frontier", "soft_budget_ratio"),
    ("cache", "l0_ttl_seconds"),
    ("cache", "l1_ttl_seconds"),
    ("cache", "l1_similarity_threshold"),
    ("boundaries", "enabled"),
    ("boundaries", "mode"),
    ("boundaries", "product_name"),
    ("boundaries", "product_description"),
    ("boundaries", "allow_topics"),
    ("boundaries", "deny_topics"),
    ("boundaries", "examples_in"),
    ("boundaries", "examples_out"),
    ("boundaries", "refuse_message"),
    ("boundaries", "clear_out_threshold"),
    ("boundaries", "clear_in_threshold"),
    ("boundaries", "stages_b0"),
    ("boundaries", "stages_b1"),
    ("boundaries", "stages_b2"),
    ("boundaries", "stages_b3"),
)


def config_file_path(settings: Any = None) -> Path:
    override = getattr(settings, "config_path", None) if settings is not None else None
    if override:
        return Path(override)
    return Path.home() / ".daari" / "config.yaml"


def load_file_document(path: Path | None = None) -> dict[str, Any]:
    target = path or config_file_path()
    if not target.is_file():
        return {}
    try:
        loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _get_nested(doc: dict[str, Any], parts: tuple[str, ...]) -> Any:
    cur: Any = doc
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


_MISSING = object()


def _file_leaf(doc: dict[str, Any], parts: tuple[str, ...]) -> Any:
    """Map editor flat cache keys onto nested yaml cache.l0/l1 shapes."""
    if parts[0] == "cache":
        cache = doc.get("cache") if isinstance(doc.get("cache"), dict) else {}
        key = parts[1]
        if key == "l0_ttl_seconds":
            l0 = cache.get("l0") if isinstance(cache.get("l0"), dict) else {}
            return l0.get("ttl_seconds", _MISSING)
        if key == "l1_ttl_seconds":
            l1 = cache.get("l1") if isinstance(cache.get("l1"), dict) else {}
            return l1.get("ttl_seconds", _MISSING)
        if key == "l1_similarity_threshold":
            l1 = cache.get("l1") if isinstance(cache.get("l1"), dict) else {}
            return l1.get("similarity_threshold", _MISSING)
    return _get_nested(doc, parts)


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, list) and isinstance(right, list):
        return list(left) == list(right)
    if isinstance(left, float) or isinstance(right, float):
        try:
            return abs(float(left) - float(right)) < 1e-9
        except (TypeError, ValueError):
            return left == right
    return left == right


def live_config_payload(settings: Any) -> dict[str, Any]:
    s = settings
    return {
        "routing": {
            "prefer": s.routing.prefer,
            "confidence_threshold": s.routing.confidence_threshold,
            "latency_budget_ms": s.routing.latency_budget_ms,
            "max_tier_for_chat": s.routing.max_tier_for_chat,
        },
        "frontier": {
            "daily_budget_usd": s.frontier.daily_budget_usd,
            "monthly_budget_usd": s.frontier.monthly_budget_usd,
            "soft_budget_ratio": s.frontier.soft_budget_ratio,
        },
        "cache": {
            "l0_ttl_seconds": s.cache.l0.ttl_seconds,
            "l1_ttl_seconds": s.cache.l1.ttl_seconds,
            "l1_similarity_threshold": s.cache.l1.similarity_threshold,
        },
        "boundaries": {
            "enabled": s.boundaries.enabled,
            "mode": s.boundaries.mode,
            "product_name": s.boundaries.product_name,
            "product_description": s.boundaries.product_description,
            "allow_topics": list(s.boundaries.allow_topics),
            "deny_topics": list(s.boundaries.deny_topics),
            "examples_in": list(s.boundaries.examples_in),
            "examples_out": list(s.boundaries.examples_out),
            "refuse_message": s.boundaries.refuse_message,
            "clear_out_threshold": s.boundaries.clear_out_threshold,
            "clear_in_threshold": s.boundaries.clear_in_threshold,
            "stages_b0": s.boundaries.stages_b0,
            "stages_b1": s.boundaries.stages_b1,
            "stages_b2": s.boundaries.stages_b2,
            "stages_b3": s.boundaries.stages_b3,
        },
    }


def field_key(parts: tuple[str, ...]) -> str:
    return ".".join(parts)


def ownership_fields(
    live: dict[str, Any],
    *,
    file_doc: dict[str, Any] | None = None,
    runtime_overrides: set[str] | frozenset[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-field source/editable/diverged metadata for the safe editor subset (#1111)."""
    doc = file_doc if file_doc is not None else {}
    overrides = set(runtime_overrides or ())
    out: dict[str, dict[str, Any]] = {}
    for parts in _FIELD_PATHS:
        key = field_key(parts)
        live_val = live[parts[0]][parts[1]]
        file_val = _file_leaf(doc, parts)
        in_file = file_val is not _MISSING
        diverged = bool(in_file and not _values_equal(live_val, file_val))
        if key in overrides or diverged:
            source = "runtime"
        elif in_file:
            source = "file"
        else:
            source = "default"
        meta: dict[str, Any] = {
            "source": source,
            "editable": True,
            "diverged": diverged or key in overrides,
        }
        if in_file and (diverged or key in overrides):
            meta["file_value"] = file_val
        out[key] = meta
    return out


def patch_field_keys(body: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for section in _SAFE_SECTIONS:
        section_body = body.get(section)
        if not isinstance(section_body, dict):
            continue
        for name in section_body:
            keys.add(f"{section}.{name}")
    return keys


EPHEMERAL_WARNING = (
    "Changes applied at runtime only; restart will reload config.yaml unless "
    "you PATCH with persist: true."
)

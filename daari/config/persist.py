"""Persist a safe config subset into ~/.daari/config.yaml (config editor deepen)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def persist_safe_config(
    patch: dict[str, Any],
    *,
    config_path: Path | None = None,
) -> Path:
    path = config_path or (Path.home() / ".daari" / "config.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            existing = loaded
    for section in ("routing", "frontier", "cache", "guardrails", "boundaries"):
        if section not in patch or not isinstance(patch[section], dict):
            continue
        if section == "cache":
            cache = dict(existing.get("cache") or {})
            body = patch["cache"]
            if "l0_ttl_seconds" in body:
                l0 = dict(cache.get("l0") or {})
                l0["ttl_seconds"] = body["l0_ttl_seconds"]
                cache["l0"] = l0
            if "l1_ttl_seconds" in body:
                l1 = dict(cache.get("l1") or {})
                l1["ttl_seconds"] = body["l1_ttl_seconds"]
                cache["l1"] = l1
            if "l1_similarity_threshold" in body:
                l1 = dict(cache.get("l1") or {})
                l1["similarity_threshold"] = body["l1_similarity_threshold"]
                cache["l1"] = l1
            existing["cache"] = cache
            continue
        base = dict(existing.get(section) or {})
        base.update(patch[section])
        existing[section] = base
    path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
    return path

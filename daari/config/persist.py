"""Persist a safe config subset into ~/.daari/config.yaml (config editor deepen)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILE_MODE = 0o600


def write_config_atomically(path: Path, document: dict[str, Any]) -> None:
    """Replace `path` in one step, owner-only.

    The file lives next to provider API keys, and a truncated write would leave
    the daemon unable to start, so serialize to a sibling temp file first and
    rename over the target.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = yaml.safe_dump(document, sort_keys=False)
    handle, tmp_name = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_path, CONFIG_FILE_MODE)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


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
    write_config_atomically(path, existing)
    return path

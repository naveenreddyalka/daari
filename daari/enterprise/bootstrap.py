"""Fleet bootstrap — fetch signed org config and write local profile (issue #118)."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any

import httpx
import yaml


def verify_signature(payload: bytes, signature_hex: str, secret: str) -> bool:
    if not secret or not signature_hex:
        return False
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature_hex.strip().lower())


def fetch_org_config(
    url: str,
    *,
    token: str = "",
    timeout: float = 10.0,
) -> tuple[dict[str, Any], bytes, str]:
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        raw = response.content
        signature = response.headers.get("x-daari-signature", "")
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("org config must be a JSON object")
        return data, raw, signature


def apply_org_config(
    config: dict[str, Any],
    *,
    config_path: Path | None = None,
    device_id: str | None = None,
) -> Path:
    """Merge org block into ~/.daari/config.yaml and register device id."""
    path = config_path or (Path.home() / ".daari" / "config.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            existing = loaded
    org = config.get("org") or config.get("enterprise") or config
    if not isinstance(org, dict):
        raise ValueError("missing org section")
    enterprise = dict(existing.get("enterprise") or existing.get("org") or {})
    enterprise.update(org)
    enterprise["enabled"] = True
    if device_id:
        enterprise["device_id"] = device_id
    existing["enterprise"] = enterprise
    # Optional safe routing/cache overrides from central policy.
    for key in ("routing", "cache", "frontier", "guardrails"):
        if isinstance(config.get(key), dict):
            base = dict(existing.get(key) or {})
            base.update(config[key])
            existing[key] = base
    path.write_text(yaml.safe_dump(existing, sort_keys=False), encoding="utf-8")
    return path

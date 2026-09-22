"""Fleet bootstrap — fetch signed org config and write local profile (issue #118)."""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from typing import Any

import httpx
import yaml

from daari.config.persist import write_config_atomically

# Integer policy-bundle schema. Major = the integer itself for now (#942).
# Older clients ignore unknown keys (including `schema`); this client refuses
# majors newer than POLICY_SCHEMA so a laptop fleet fails closed on skew.
POLICY_SCHEMA = 1


class PolicySchemaError(ValueError):
    """Raised when a policy bundle declares an unsupported schema major."""


def validate_policy_schema(config: dict[str, Any]) -> None:
    """Accept missing/legacy schema or schema <= POLICY_SCHEMA; refuse unknowns."""
    if "schema" not in config:
        return
    raw = config.get("schema")
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise PolicySchemaError(f"policy schema must be an integer major, got {raw!r}")
    if raw > POLICY_SCHEMA:
        raise PolicySchemaError(
            f"unknown policy schema major {raw}; this daari supports <= {POLICY_SCHEMA}"
        )


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
    validate_policy_schema(config)
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
    write_config_atomically(path, existing)
    return path

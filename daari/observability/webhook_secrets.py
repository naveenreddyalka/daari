"""Webhook signing-secret rotation with dual-secret grace (#1680)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_FAMILY_KEYS = {
    "budget": {
        "current": "budget_webhook_secret",
        "previous": "budget_webhook_secret_previous",
        "rotated_at": "budget_webhook_secret_rotated_at",
    },
    "key-expiry": {
        "current": "key_expiry_webhook_secret",
        "previous": "key_expiry_webhook_secret_previous",
        "rotated_at": "key_expiry_webhook_secret_rotated_at",
    },
}


def rotate_webhook_secret_in_config(
    path: Path,
    *,
    family: str,
    new_secret: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Move current→previous and write ``new_secret`` as current in config.yaml.

    Returns metadata for CLI/audit (rotated_at, had_previous). Signing always
    uses the new current; receivers verify against either during grace.
    """
    keys = _FAMILY_KEYS.get(family)
    if keys is None:
        raise ValueError(f"unknown webhook family {family!r}")
    secret = (new_secret or "").strip()
    if not secret:
        raise ValueError("new secret must be non-empty")
    path = Path(path)
    current_doc: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if isinstance(loaded, dict):
            current_doc = loaded
    alerts = current_doc.setdefault("alerts", {})
    if not isinstance(alerts, dict):
        alerts = {}
        current_doc["alerts"] = alerts
    old_current = str(alerts.get(keys["current"]) or "").strip()
    had_previous = bool(str(alerts.get(keys["previous"]) or "").strip())
    if old_current and old_current != secret:
        alerts[keys["previous"]] = old_current
        had_previous = True
    alerts[keys["current"]] = secret
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    rotated_at = moment.astimezone(timezone.utc).isoformat()
    alerts[keys["rotated_at"]] = rotated_at
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(current_doc, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return {
        "family": family,
        "rotated_at": rotated_at,
        "had_previous": had_previous or bool(old_current),
        "config": str(path),
    }

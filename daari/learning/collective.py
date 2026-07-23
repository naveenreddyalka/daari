"""Phase D3: opt-in anonymized collective stats (roadmap D3/D4).

Aggregates routing evidence into a payload the user can review before
anything leaves the device: category/tier outcome rates, latency averages,
shadow-sampling false-hit rates, model IDs, platform, and daari version.
Never includes prompt text, completions, file paths, client IDs, or trace
IDs — the export is built exclusively from FeedbackStore aggregates.
"""

from __future__ import annotations

import platform
from datetime import datetime, timezone
from typing import Any

import httpx

import daari
from daari.config.settings import Settings
from daari.learning.feedback import FeedbackStore

SCHEMA_VERSION = 1

# Guard rail pinned by tests: keys that must never appear anywhere in the
# exported payload.
FORBIDDEN_KEYS = {"prompt", "completion", "messages", "content", "client_id", "trace_id"}


def build_collective_stats(
    settings: Settings,
    feedback_store: FeedbackStore,
    *,
    days: int = 30,
) -> dict[str, Any]:
    """Build the reviewable, metadata-only stats payload."""
    return {
        "schema": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "daari_version": daari.__version__,
        "platform": {"system": platform.system(), "machine": platform.machine()},
        "models": {
            "l3": settings.models.l3,
            "l4": settings.models.l4,
            "l5": settings.models.l5,
        },
        "window_days": days,
        # Per (category, tier): outcome counts, escalation/reject rates,
        # avg confidence and latency — aggregates only.
        "categories": feedback_store.stats(days=days),
        # Per category: shadow-sampled semantic-cache false-hit rate.
        "cache_trust": feedback_store.shadow_stats(days=days),
    }


def payload_is_clean(payload: Any) -> bool:
    """Recursively verify no forbidden keys leaked into the payload."""
    if isinstance(payload, dict):
        return all(
            key not in FORBIDDEN_KEYS and payload_is_clean(value)
            for key, value in payload.items()
        )
    if isinstance(payload, list):
        return all(payload_is_clean(item) for item in payload)
    return True


def upload_collective_stats(
    payload: dict[str, Any],
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> int:
    """POST the payload to the configured endpoint. Opt-in is enforced here
    too, so no code path can upload without both the flag and a URL."""
    learning = settings.learning
    if not learning.collective_enabled:
        raise RuntimeError("collective stats upload is disabled (learning.collective_enabled)")
    url = learning.collective_url.strip()
    if not url:
        raise RuntimeError("no learning.collective_url configured")
    if not payload_is_clean(payload):
        raise RuntimeError("payload failed the sensitive-key guard; refusing to upload")
    headers = {}
    if learning.collective_token:
        headers["Authorization"] = f"Bearer {learning.collective_token}"
    own_client = client is None
    http = client or httpx.Client(timeout=10.0)
    try:
        response = http.post(url, json=payload, headers=headers)
        return response.status_code
    finally:
        if own_client:
            http.close()

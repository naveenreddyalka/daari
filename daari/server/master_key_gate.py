"""Refuse weak or unset master keys at ``daari serve`` (#1320).

LiteLLM-style default-deny for empty / publicly known master keys, with an
explicit escape hatch for hermetic tests and local sandboxes.
"""

from __future__ import annotations

import sys
from typing import Any

WEAK_MASTER_KEYS = frozenset(
    {
        "sk-1234",
        "changeme",
        "daari-local",
        "replace-me",
        "secret",
        "password",
        "test",
        "testing",
    }
)


def master_key_gate_error(settings: Any) -> str | None:
    """Return a stderr-ready message when serve must refuse, else None."""
    server = getattr(settings, "server", None)
    if server is None:
        return None
    if bool(getattr(server, "dangerously_permit_weak_or_unset_api_key", False)):
        return None

    raw = getattr(server, "api_key", "")
    keys = list(getattr(server, "master_keys", lambda: [])())
    if not keys:
        # Distinguish configured-but-blank from truly unset for the message.
        if isinstance(raw, list):
            source = "server.api_key (list empty after trim)"
        elif isinstance(raw, str) and raw.strip() == "" and raw != "":
            source = "server.api_key (whitespace only)"
        else:
            source = "server.api_key (unset/empty)"
        return (
            f"refusing to serve: {source} — set a strong master key, or set "
            "server.dangerously_permit_weak_or_unset_api_key: true for local sandboxes"
        )

    for key in keys:
        if key.strip().lower() in WEAK_MASTER_KEYS:
            return (
                f"refusing to serve: server.api_key matches weak denylist "
                f"({key.strip().lower()!r}) — choose a unique secret, or set "
                "server.dangerously_permit_weak_or_unset_api_key: true for local sandboxes"
            )
    return None


def require_strong_master_key(settings: Any, *, file=None) -> None:
    """Exit process with code 1 when the master key gate fails."""
    message = master_key_gate_error(settings)
    if message is None:
        return
    stream = file or sys.stderr
    print(f"  ✗ master_key: {message}", file=stream)
    raise SystemExit(1)

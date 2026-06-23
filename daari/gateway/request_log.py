from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LOG_PATH = Path.home() / ".daari" / "cursor-requests.log"


def log_gateway_event(event: str, payload: dict[str, Any]) -> None:
    """Append JSON lines for Cursor/BYOK debugging."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        with LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass

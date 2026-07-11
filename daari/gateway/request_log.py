from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = Path.home() / ".daari" / "cursor-requests.log"
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUPS = 3

LOG_PATH = DEFAULT_LOG_PATH
_max_bytes = DEFAULT_MAX_BYTES
_backups = DEFAULT_BACKUPS
_lock = threading.Lock()


def configure_request_log(
    *,
    path: Path | str | None = None,
    max_bytes: int | None = None,
    backups: int | None = None,
) -> None:
    """Apply settings at daemon startup; max_bytes=0 disables rotation."""
    global LOG_PATH, _max_bytes, _backups
    if path is not None:
        LOG_PATH = Path(path)
    if max_bytes is not None:
        _max_bytes = max(0, int(max_bytes))
    if backups is not None:
        _backups = max(1, int(backups))


def _rotate_if_needed() -> None:
    if _max_bytes <= 0:
        return
    try:
        if not LOG_PATH.exists() or LOG_PATH.stat().st_size < _max_bytes:
            return
        oldest = LOG_PATH.with_name(f"{LOG_PATH.name}.{_backups}")
        oldest.unlink(missing_ok=True)
        for index in range(_backups - 1, 0, -1):
            source = LOG_PATH.with_name(f"{LOG_PATH.name}.{index}")
            if source.exists():
                source.rename(LOG_PATH.with_name(f"{LOG_PATH.name}.{index + 1}"))
        LOG_PATH.rename(LOG_PATH.with_name(f"{LOG_PATH.name}.1"))
    except OSError:
        # Concurrent rotation races are tolerable; losing a rotation beats
        # failing the request that triggered the log write.
        pass


def log_gateway_event(event: str, payload: dict[str, Any]) -> None:
    """Append JSON lines for Cursor/BYOK debugging."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        with _lock:
            _rotate_if_needed()
            with LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")
    except OSError:
        pass

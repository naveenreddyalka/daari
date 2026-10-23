"""Fleet-shared cancel signals for Responses background jobs (#1874).

Single-node keeps process-local tasks (``_BACKGROUND_JOBS`` in responses.py).
When ``cache.backend=redis``, cancel/delete from any replica sets a Redis flag
so the owning pod's cooperative watcher can ``task.cancel()`` the in-flight job.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from daari.gateway.request_log import log_gateway_event

_CANCEL_KEY_PREFIX = "daari:responses:bg_cancel:"
_CANCEL_TTL_SECONDS = 3600
_WATCH_INTERVAL_SECONDS = 0.05

# Shared backend: None = local in-process flags only; Redis-like client when fleet.
_backend: Any | None = None
_backend_name: str = "local"
_local_flags: set[str] = set()
_LOCAL_JOBS: dict[str, asyncio.Task[None]] = {}
_watcher_task: asyncio.Task[None] | None = None


def reset_job_cancel_coordinator() -> None:
    """Clear module state (tests + shutdown)."""
    global _backend, _backend_name, _watcher_task
    _backend = None
    _backend_name = "local"
    _local_flags.clear()
    _LOCAL_JOBS.clear()
    if _watcher_task is not None and not _watcher_task.done():
        _watcher_task.cancel()
    _watcher_task = None


def set_job_cancel_backend(client: Any | None) -> None:
    """Install (or clear) a Redis-like shared cancel store (tests + startup)."""
    global _backend, _backend_name
    _backend = client
    _backend_name = "redis" if client is not None else "local"


def job_cancel_backend_name() -> str:
    return _backend_name


def configure_job_cancel_store(
    settings: Any,
    *,
    connect_redis: Callable[..., Any] | None = None,
) -> None:
    """Wire Redis cancel flags when ``cache.backend=redis`` (#1874)."""
    cache = getattr(settings, "cache", None)
    if getattr(cache, "backend", "disk") != "redis":
        set_job_cancel_backend(None)
        return
    url = str(getattr(cache, "redis_url", "") or "").strip()
    if not url:
        set_job_cancel_backend(None)
        return
    try:
        connect = connect_redis
        if connect is None:
            from daari.cache.redis_client import connect_redis as connect

        timeout = float(getattr(cache, "redis_timeout_seconds", 2.0) or 2.0)
        set_job_cancel_backend(connect(url, timeout_seconds=timeout))
    except Exception:
        log_gateway_event("responses_job_cancel_redis_error", {"op": "connect"})
        set_job_cancel_backend(None)


def _cancel_key(response_id: str) -> str:
    return f"{_CANCEL_KEY_PREFIX}{response_id}"


def signal_cancel(response_id: str) -> None:
    """Mark cancel for ``response_id`` and cancel a local task if present."""
    if not response_id:
        return
    _local_flags.add(response_id)
    if _backend is not None:
        try:
            _backend.set(_cancel_key(response_id), "1", ex=_CANCEL_TTL_SECONDS)
        except Exception:
            log_gateway_event(
                "responses_job_cancel_redis_error",
                {"op": "set", "response_id": response_id},
            )
    job = _LOCAL_JOBS.pop(response_id, None)
    if job is not None and not job.done():
        job.cancel()


def is_cancel_requested(response_id: str) -> bool:
    if not response_id:
        return False
    if response_id in _local_flags:
        return True
    if _backend is None:
        return False
    try:
        raw = _backend.get(_cancel_key(response_id))
        return bool(raw)
    except Exception:
        log_gateway_event(
            "responses_job_cancel_redis_error",
            {"op": "get", "response_id": response_id},
        )
        return False


def clear_cancel(response_id: str) -> None:
    """Drop cancel flag after a job finishes (best-effort)."""
    if not response_id:
        return
    _local_flags.discard(response_id)
    if _backend is None:
        return
    try:
        _backend.delete(_cancel_key(response_id))
    except Exception:
        log_gateway_event(
            "responses_job_cancel_redis_error",
            {"op": "delete", "response_id": response_id},
        )


def register_local_job(response_id: str, task: asyncio.Task[None]) -> None:
    """Track an in-process background task so fleet cancel can stop it."""
    if not response_id:
        return
    _LOCAL_JOBS[response_id] = task

    def _done(_t: asyncio.Task[None], rid: str = response_id) -> None:
        _LOCAL_JOBS.pop(rid, None)

    task.add_done_callback(_done)


def unregister_local_job(response_id: str) -> asyncio.Task[None] | None:
    return _LOCAL_JOBS.pop(response_id, None)


async def _watch_loop() -> None:
    while True:
        try:
            await asyncio.sleep(_WATCH_INTERVAL_SECONDS)
            # Snapshot ids — signal_cancel may mutate the dict.
            for rid in list(_LOCAL_JOBS.keys()):
                if not is_cancel_requested(rid):
                    continue
                job = _LOCAL_JOBS.pop(rid, None)
                if job is not None and not job.done():
                    job.cancel()
                    log_gateway_event(
                        "responses_background_fleet_cancel",
                        {"response_id": rid},
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            log_gateway_event("responses_job_cancel_watcher_error", {})


def ensure_cancel_watcher() -> None:
    """Start the cooperative cancel poller once per process when needed."""
    global _watcher_task
    if _backend is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _watcher_task is not None and not _watcher_task.done():
        return
    _watcher_task = loop.create_task(_watch_loop())

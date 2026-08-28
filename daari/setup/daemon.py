from __future__ import annotations

import sys
import time
from collections.abc import Callable

import httpx

from daari.config.settings import Settings


def local_daemon_healthy(
    settings: Settings,
    *,
    httpx_client: httpx.Client | None = None,
) -> bool:
    url = f"http://{settings.server.host}:{settings.server.port}/health"
    own = httpx_client is None
    http = httpx_client or httpx.Client(timeout=2.0)
    try:
        return http.get(url).status_code == 200
    except Exception:
        return False
    finally:
        if own:
            http.close()


def spawn_local_daemon(settings: Settings) -> None:
    import subprocess

    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "daari",
            "serve",
            "--host",
            settings.server.host,
            "--port",
            str(settings.server.port),
        ],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def ensure_local_daemon(
    settings: Settings,
    *,
    health_fn: Callable[[], bool] | None = None,
    spawn_fn: Callable[[], None] | None = None,
    wait_seconds: float = 15.0,
    poll_interval: float = 0.25,
) -> bool:
    check = health_fn or (lambda: local_daemon_healthy(settings))
    if check():
        return True
    spawn = spawn_fn or (lambda: spawn_local_daemon(settings))
    spawn()
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        if check():
            return True
        time.sleep(poll_interval)
    return False

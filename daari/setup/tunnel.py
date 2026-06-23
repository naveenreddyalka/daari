from __future__ import annotations

import re
import time
from collections.abc import Callable, Iterable
from urllib.parse import urlparse

import httpx

_TUNNEL_URL_PATTERN = re.compile(r"https://[a-zA-Z0-9.-]+\.trycloudflare\.com")
_METRICS_PORT_PATTERN = re.compile(r"Starting metrics server on 127\.0\.0\.1:(\d+)/metrics")
_CLOUDFLARED_READY_PATTERN = re.compile(
    r"(precheck complete|Registered tunnel connection)",
    re.IGNORECASE,
)

DEFAULT_TUNNEL_HEALTH_TIMEOUT_SECONDS = 60.0
INITIAL_TUNNEL_HEALTH_BACKOFF_SECONDS = 0.5
MAX_TUNNEL_HEALTH_BACKOFF_SECONDS = 4.0


def parse_cloudflared_tunnel_url(line: str) -> str | None:
    """Extract a public trycloudflare URL from one output line."""
    match = _TUNNEL_URL_PATTERN.search(line)
    if match is None:
        return None
    candidate = match.group(0)
    parsed = urlparse(candidate)
    host = parsed.hostname or ""
    if host == "api.trycloudflare.com":
        return None
    return candidate


def find_cloudflared_tunnel_url(lines: Iterable[str]) -> str | None:
    """Return first tunnel URL seen in cloudflared output."""
    for line in lines:
        url = parse_cloudflared_tunnel_url(line)
        if url:
            return url
    return None


def cloudflared_tunnel_ready_from_logs(text: str) -> bool:
    """Return True once cloudflared reports the tunnel connection is up."""
    return _CLOUDFLARED_READY_PATTERN.search(text) is not None


def parse_cloudflared_metrics_port(line: str) -> int | None:
    """Extract the local metrics port from one cloudflared output line."""
    match = _METRICS_PORT_PATTERN.search(line)
    if match is None:
        return None
    return int(match.group(1))


def find_cloudflared_metrics_port(lines: Iterable[str]) -> int | None:
    """Return first metrics port seen in cloudflared output."""
    for line in lines:
        port = parse_cloudflared_metrics_port(line)
        if port is not None:
            return port
    return None


def tunnel_health_ok(tunnel_url: str, *, timeout: float = 5.0) -> bool:
    """Probe the public tunnel /health endpoint."""
    try:
        response = httpx.get(f"{tunnel_url.rstrip('/')}/health", timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def wait_for_tunnel_health(
    tunnel_url: str,
    *,
    timeout_seconds: float = DEFAULT_TUNNEL_HEALTH_TIMEOUT_SECONDS,
    initial_backoff_seconds: float = INITIAL_TUNNEL_HEALTH_BACKOFF_SECONDS,
    max_backoff_seconds: float = MAX_TUNNEL_HEALTH_BACKOFF_SECONDS,
    probe: Callable[[str], bool] | None = None,
) -> bool:
    """Retry tunnel health probes with exponential backoff."""
    probe_fn = probe or tunnel_health_ok
    deadline = time.monotonic() + timeout_seconds
    backoff = initial_backoff_seconds
    while time.monotonic() < deadline:
        if probe_fn(tunnel_url):
            return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(backoff, remaining, max_backoff_seconds))
        backoff = min(backoff * 2, max_backoff_seconds)
    return False

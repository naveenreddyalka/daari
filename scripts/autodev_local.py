"""Testable helpers for scripts/autodev-local.sh (issue #181).

The launchd watchdog used to treat a single 5s /health probe as authoritative,
which filed false "daemon unreachable" regressions while the same cycle's smoke
test passed once serve finished booting. Poll /ready (then /health) with bounded
backoff instead.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import httpx

DEFAULT_DAEMON_WAIT_TIMEOUT_SECONDS = 30.0
INITIAL_DAEMON_BACKOFF_SECONDS = 1.0
MAX_DAEMON_BACKOFF_SECONDS = 5.0


def _default_probe(url: str, *, timeout: float = 5.0) -> bool:
    try:
        response = httpx.get(url, timeout=timeout)
        return response.status_code == 200
    except Exception:
        return False


def daemon_ready(
    base_url: str,
    *,
    probe: Callable[[str], bool] | None = None,
) -> bool:
    """Return True when the daemon responds on /ready, else /health."""
    root = base_url.rstrip("/")
    probe_fn = probe or _default_probe
    if probe_fn(f"{root}/ready"):
        return True
    return probe_fn(f"{root}/health")


def wait_for_daemon(
    base_url: str,
    *,
    timeout_seconds: float = DEFAULT_DAEMON_WAIT_TIMEOUT_SECONDS,
    initial_backoff_seconds: float = INITIAL_DAEMON_BACKOFF_SECONDS,
    max_backoff_seconds: float = MAX_DAEMON_BACKOFF_SECONDS,
    probe: Callable[[str], bool] | None = None,
    sleep: Callable[[float], Any] | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    """Poll daemon readiness with exponential backoff until timeout."""
    probe_fn = probe or (lambda _root: daemon_ready(base_url))
    deadline = monotonic() + timeout_seconds
    backoff = initial_backoff_seconds
    while monotonic() < deadline:
        if probe_fn(base_url):
            return True
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        delay = min(backoff, remaining, max_backoff_seconds)
        if sleep is not None:
            sleep(delay)
        else:
            time.sleep(delay)
        backoff = min(backoff * 2, max_backoff_seconds)
    return False


def failures_fingerprint(failures: list[str]) -> str:
    """Stable identity for watchdog failure bullets (issue #1337)."""
    return "\n".join(sorted(item.strip() for item in failures if item.strip()))


def parse_failures_section(body: str) -> list[str]:
    """Extract `- ` bullets under the first `## Failures` heading."""
    marker = "## Failures"
    text = body or ""
    if marker not in text:
        return []
    after = text.split(marker, 1)[1]
    bullets: list[str] = []
    for line in after.splitlines():
        stripped = line.strip()
        if stripped.startswith("## ") and not stripped.startswith("## Failures"):
            break
        if stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    return bullets


def open_issue_has_same_failures(open_bodies: list[str], failures: list[str]) -> bool:
    """True when an open regression body lists the same failure bullets."""
    needle = failures_fingerprint(failures)
    if not needle:
        return False
    return any(failures_fingerprint(parse_failures_section(body)) == needle for body in open_bodies)


def should_skip_regression_create(
    nodes: list[dict[str, Any]],
    title: str,
    failures: list[str],
) -> bool:
    """Skip when title matches or an open body lists the same failures."""
    for node in nodes:
        if (node.get("title") or "") == title:
            return True
        if open_issue_has_same_failures([str(node.get("body") or "")], failures):
            return True
    return False


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "wait":
        return 0 if wait_for_daemon(args[1]) else 1
    if len(args) == 2 and args[0] == "ready":
        return 0 if daemon_ready(args[1]) else 1
    if len(args) >= 1 and args[0] == "skip-create":
        import json

        payload = json.loads(sys.stdin.read() or "{}")
        nodes = (
            payload.get("data", {})
            .get("repository", {})
            .get("issues", {})
            .get("nodes")
            or []
        )
        if not isinstance(nodes, list):
            nodes = []
        title = args[1] if len(args) > 1 else ""
        failures = args[2:]
        return 0 if should_skip_regression_create(nodes, title, failures) else 1
    print(
        "usage: autodev_local.py {wait|ready} <daemon-base-url>"
        " | skip-create <title> <failure> ...  # GraphQL JSON on stdin",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

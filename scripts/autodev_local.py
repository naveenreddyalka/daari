"""Testable helpers for scripts/autodev-local.sh (issue #181).

The launchd watchdog used to treat a single 5s /health probe as authoritative,
which filed false "daemon unreachable" regressions while the same cycle's smoke
test passed once serve finished booting. Poll /ready (then /health) with bounded
backoff instead.

Fatal-config stderr (master_key refuse, #1453) must not busy-kickstart: classify
the serve.err.log tail and skip KeepAlive-style restarts for that watchdog cycle.

Cursor smoke (#1425) always overwrites smoke-latest.json — including on
ConnectError — so FAIL logs never echo a prior cycle's 200 / content_chunks.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

import httpx

DEFAULT_DAEMON_WAIT_TIMEOUT_SECONDS = 30.0
INITIAL_DAEMON_BACKOFF_SECONDS = 1.0
MAX_DAEMON_BACKOFF_SECONDS = 5.0

# Substrings / regexes matching hard serve refusals (2026-10-05 crash-loop tails).
_FATAL_CONFIG_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "master_key_refuse",
        re.compile(
            r"master_key:.*refusing to serve|refusing to serve:.*server\.api_key",
            re.IGNORECASE,
        ),
    ),
    (
        "hard_refuse",
        re.compile(r"refusing to serve:", re.IGNORECASE),
    ),
)


class FatalServeConfig(NamedTuple):
    """Classified fatal-config hit from daari serve stderr (#1453)."""

    reason: str
    matched: str


def classify_fatal_serve_config(stderr_text: str | None) -> FatalServeConfig | None:
    """Return a hit when stderr shows a fatal config refuse, else None."""
    text = stderr_text or ""
    if not text.strip():
        return None
    for reason, pattern in _FATAL_CONFIG_RULES:
        match = pattern.search(text)
        if match is not None:
            line = match.group(0).strip()
            for raw in text.splitlines():
                if match.group(0) in raw:
                    line = raw.strip()
                    break
            return FatalServeConfig(reason=reason, matched=line)
    return None


def should_skip_serve_kickstart(hit: FatalServeConfig | None) -> bool:
    """True when kickstart / KeepAlive restart would only spam the same refuse."""
    return hit is not None


def daemon_unreachable_failure_bullet(hit: FatalServeConfig | None) -> str:
    """Failure bullet for issue bodies; includes classified reason when present."""
    if hit is None:
        return "daemon unreachable"
    return f"daemon unreachable (fatal config: {hit.reason})"


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


class CursorSmokeResult(NamedTuple):
    """Outcome of the Cursor-shaped streaming smoke probe (#1425)."""

    ok: bool
    status_code: int | None
    content_chunks: int
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status_code": self.status_code,
            "content_chunks": self.content_chunks,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def _count_content_delta_chunks(stream_text: str) -> int:
    return sum(
        1 for ln in (stream_text or "").splitlines() if '"content"' in ln and '"delta"' in ln
    )


def _cursor_smoke_payload() -> dict[str, Any]:
    tools = [
        {
            "type": "function",
            "function": {
                "name": f"tool_{i}",
                "description": "ide tool",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for i in range(18)
    ]
    return {
        "model": "daari",
        "stream": True,
        "stream_options": {"include_usage": True},
        "messages": [
            {"role": "system", "content": "You are a coding assistant with tools."},
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "What is 2 plus 2?"}],
            },
        ],
        "tools": tools,
    }


def run_cursor_smoke(
    daemon_url: str,
    out_path: str | Path,
    *,
    post: Callable[..., Any] | None = None,
    timeout: float = 120.0,
) -> CursorSmokeResult:
    """POST a Cursor-shaped stream request; always overwrite out_path (#1425).

    A prior-run success JSON must never survive a ConnectError — the watchdog
    used to `cat smoke-latest.json` after an uncaught exception and log a
    false 200 / content_chunks > 0 from the previous cycle.
    """
    import json

    path = Path(out_path)
    root = daemon_url.rstrip("/")
    post_fn = post or (lambda url, **kwargs: httpx.post(url, **kwargs))
    try:
        response = post_fn(
            f"{root}/v1/chat/completions",
            json=_cursor_smoke_payload(),
            timeout=timeout,
        )
        status = int(getattr(response, "status_code", 0) or 0)
        chunks = _count_content_delta_chunks(str(getattr(response, "text", "") or ""))
        result = CursorSmokeResult(
            ok=status == 200 and chunks > 0,
            status_code=status,
            content_chunks=chunks,
        )
    except Exception as exc:  # noqa: BLE001 — surface any transport failure to the JSON
        result = CursorSmokeResult(
            ok=False,
            status_code=None,
            content_chunks=0,
            error=f"{type(exc).__name__}: {exc}",
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.as_dict()), encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "wait":
        return 0 if wait_for_daemon(args[1]) else 1
    if len(args) == 2 and args[0] == "ready":
        return 0 if daemon_ready(args[1]) else 1
    if len(args) >= 1 and args[0] == "classify-fatal":
        # Exit 0 + print reason when stderr is fatal-config; exit 1 when not.
        path = args[1] if len(args) > 1 else "-"
        if path == "-":
            text = sys.stdin.read()
        else:
            try:
                text = open(path, encoding="utf-8", errors="replace").read()
            except OSError:
                return 1
        hit = classify_fatal_serve_config(text)
        if hit is None:
            return 1
        print(hit.reason)
        return 0
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
    if len(args) == 3 and args[0] == "cursor-smoke":
        result = run_cursor_smoke(args[1], args[2])
        print(f"smoke: {result.as_dict()}")
        return 0 if result.ok else 1
    print(
        "usage: autodev_local.py {wait|ready} <daemon-base-url>"
        " | classify-fatal [stderr-path|-]"
        " | cursor-smoke <daemon-base-url> <out-json-path>"
        " | skip-create <title> <failure> ...  # GraphQL JSON on stdin",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

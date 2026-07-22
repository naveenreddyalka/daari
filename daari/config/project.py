"""Per-project profiles from .daari.yaml (issue #91, roadmap C1).

Clients declare their repo with `X-Daari-Project: /path/inside/repo`; the
gateway walks up to find `.daari.yaml` and applies a safe subset of routing
overrides as request-meta defaults. Explicit headers always win.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

import yaml

from daari.gateway.internal import RequestMeta

PROJECT_FILE = ".daari.yaml"
_VALID_TIER_CAPS = {"L3", "L4", "L5"}

TEMPLATE = """\
# daari per-project profile — commit this at your repo root.
# Clients opt in by sending the X-Daari-Project header with a path inside
# the repo. Explicit per-request headers always win over these defaults.

routing:
  # Highest local tier for chat in this repo (L3 | L4 | L5).
  # max_tier_for_chat: L3

  # Never escalate this repo's prompts to the frontier (L6).
  # no_frontier: true

  # Max acceptable local-model latency for this repo, in milliseconds.
  # latency_budget_ms: 3000

# Ledger attribution for `daari report` (defaults to the client name).
# client_id: my-repo
"""


@dataclass(frozen=True)
class ProjectProfile:
    tier_cap: str | None = None
    no_frontier: bool = False
    latency_budget_ms: int | None = None
    client_id: str | None = None
    source: str = ""


_lock = threading.Lock()
# path -> (mtime, profile) so repeated requests don't re-read the file.
_cache: dict[str, tuple[float, ProjectProfile]] = {}


def find_project_file(start: str | Path) -> Path | None:
    """Walk up from `start` looking for .daari.yaml; tolerate bad paths."""
    try:
        current = Path(start).expanduser().resolve()
    except (OSError, ValueError):
        return None
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        project_file = candidate / PROJECT_FILE
        try:
            if project_file.is_file():
                return project_file
        except OSError:
            return None
    return None


def _parse_profile(path: Path) -> ProjectProfile:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return ProjectProfile(source=str(path))
    if not isinstance(loaded, dict):
        return ProjectProfile(source=str(path))

    routing = loaded.get("routing")
    if not isinstance(routing, dict):
        routing = {}

    tier_cap = routing.get("max_tier_for_chat")
    if not (isinstance(tier_cap, str) and tier_cap.upper() in _VALID_TIER_CAPS):
        tier_cap = None
    else:
        tier_cap = tier_cap.upper()

    latency = routing.get("latency_budget_ms")
    if not (isinstance(latency, int) and not isinstance(latency, bool) and latency > 0):
        latency = None

    client_id = loaded.get("client_id")
    if not (isinstance(client_id, str) and client_id.strip()):
        client_id = None
    else:
        client_id = client_id.strip()

    return ProjectProfile(
        tier_cap=tier_cap,
        no_frontier=routing.get("no_frontier") is True,
        latency_budget_ms=latency,
        client_id=client_id,
        source=str(path),
    )


def load_project_profile(start: str | Path | None) -> ProjectProfile | None:
    """Resolve and parse the profile for a declared project path, with caching."""
    if not start:
        return None
    project_file = find_project_file(start)
    if project_file is None:
        return None
    key = str(project_file)
    try:
        mtime = project_file.stat().st_mtime
    except OSError:
        return None
    with _lock:
        cached = _cache.get(key)
        if cached is not None and cached[0] == mtime:
            return cached[1]
    profile = _parse_profile(project_file)
    with _lock:
        _cache[key] = (mtime, profile)
    return profile


def apply_profile_to_meta(meta: RequestMeta, profile: ProjectProfile | None) -> None:
    """Fill unset meta fields from the profile; explicit values keep precedence."""
    if profile is None:
        return
    if meta.tier_cap is None and profile.tier_cap:
        meta.tier_cap = profile.tier_cap
    if profile.no_frontier:
        meta.no_frontier = True
    if meta.latency_budget_ms is None and profile.latency_budget_ms:
        meta.latency_budget_ms = profile.latency_budget_ms
    if meta.client_id is None and profile.client_id:
        meta.client_id = profile.client_id

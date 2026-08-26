from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class GtmSnapshot:
    stars: int
    forks: int
    unique_viewers_14d: int
    views_14d: int
    unique_cloners_14d: int
    clones_14d: int
    pypi_last_month: int
    pypi_last_week: int
    referrers: tuple[tuple[str, int], ...]
    generated_at: str


def viewer_drought(snap: GtmSnapshot) -> bool:
    return snap.unique_viewers_14d == 0


def render_scoreboard(snap: GtmSnapshot) -> str:
    status = "drought — unique viewers (14d) are 0" if viewer_drought(snap) else "healthy"
    referrer_rows = (
        "\n".join(f"| {name} | {count} |" for name, count in snap.referrers)
        or "| (none) | 0 |"
    )
    return f"""# GTM scoreboard

Generated: `{snap.generated_at}`

Refresh: `python scripts/gtm_scoreboard.py` (needs `gh` + network). Pytest uses fixtures only.

## Status

{status}

## Snapshot

| Metric | Value |
|--------|-------|
| Stars | {snap.stars} |
| Forks | {snap.forks} |
| Views (14d) | {snap.views_14d} |
| Unique viewers (14d) | {snap.unique_viewers_14d} |
| Clones (14d) | {snap.clones_14d} |
| Unique cloners (14d) | {snap.unique_cloners_14d} |
| PyPI downloads (30d) | {snap.pypi_last_month} |
| PyPI downloads (7d) | {snap.pypi_last_week} |

## Referrers (14d)

| Referrer | Views |
|----------|-------|
{referrer_rows}

Clone >> view usually means CI / watchdog, not humans. Treat unique viewers as the launch KPI.
"""


def write_scoreboard(path: Path, snap: GtmSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_scoreboard(snap), encoding="utf-8")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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


def render_weekly_report(
    snap: GtmSnapshot,
    shipped: tuple[str, ...] = (),
    waiting: tuple[str, ...] = (),
) -> str:
    ratio = (
        f"{snap.clones_14d / snap.views_14d:.1f}x more clones than views"
        if snap.views_14d
        else "no page views"
    )
    audience = (
        "Viewer drought."
        if viewer_drought(snap)
        else (
            f"{snap.unique_viewers_14d} unique viewers and {snap.views_14d} views "
            f"over 14 days. {snap.clones_14d} clones ({ratio}) — treat clones as "
            "automation, not humans."
        )
    )
    shipped_md = "\n".join(f"- {item}" for item in shipped) or "- (none recorded)"
    waiting_md = "\n".join(f"- {item}" for item in waiting) or "- (none recorded)"
    next_action = (
        waiting[0]
        if waiting
        else "Refresh this report after the next public post and compare unique viewers."
    )
    return f"""# GTM weekly report

Generated: `{snap.generated_at}`

Refresh: `python scripts/gtm_scoreboard.py --report`

## Verdict

{audience}

Stars {snap.stars}. Forks {snap.forks}. PyPI {snap.pypi_last_week} last week / {snap.pypi_last_month} last 30 days.

## Shipped

{shipped_md}

## Waiting

{waiting_md}

## Next

{next_action}
"""


def write_weekly_report(
    path: Path,
    snap: GtmSnapshot,
    shipped: tuple[str, ...] = (),
    waiting: tuple[str, ...] = (),
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_weekly_report(snap, shipped, waiting), encoding="utf-8")


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

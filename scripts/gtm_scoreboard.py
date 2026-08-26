#!/usr/bin/env python3
"""Refresh docs/gtm/SCOREBOARD.md from GitHub + PyPI. Never posts anywhere."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from daari.gtm.scoreboard import (  # noqa: E402
    GtmSnapshot,
    now_utc,
    viewer_drought,
    write_scoreboard,
)

REPO = "naveenreddyalka/daari"
OUT = ROOT / "docs" / "gtm" / "SCOREBOARD.md"


def _gh_json(path: str) -> dict:
    raw = subprocess.check_output(["gh", "api", path], text=True)
    return json.loads(raw)


def _pypi_recent() -> dict:
    url = "https://pypistats.org/api/packages/daari/recent"
    with urllib.request.urlopen(url, timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode())["data"]


def collect() -> GtmSnapshot:
    repo = _gh_json(f"repos/{REPO}")
    views = _gh_json(f"repos/{REPO}/traffic/views")
    clones = _gh_json(f"repos/{REPO}/traffic/clones")
    referrers = _gh_json(f"repos/{REPO}/traffic/popular/referrers")
    pypi = _pypi_recent()
    return GtmSnapshot(
        stars=int(repo.get("stargazers_count") or 0),
        forks=int(repo.get("forks_count") or 0),
        unique_viewers_14d=int(views.get("uniques") or 0),
        views_14d=int(views.get("count") or 0),
        unique_cloners_14d=int(clones.get("uniques") or 0),
        clones_14d=int(clones.get("count") or 0),
        pypi_last_month=int(pypi.get("last_month") or 0),
        pypi_last_week=int(pypi.get("last_week") or 0),
        referrers=tuple((str(r["referrer"]), int(r["count"])) for r in referrers[:8]),
        generated_at=now_utc(),
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--help" in argv or "-h" in argv:
        print("Usage: python scripts/gtm_scoreboard.py [--check-drought]")
        return 0
    snap = collect()
    write_scoreboard(OUT, snap)
    print(f"wrote {OUT}")
    if "--check-drought" in argv and viewer_drought(snap):
        print("drought: unique viewers (14d) == 0", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

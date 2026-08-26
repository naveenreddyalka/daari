"""GTM-2: scoreboard renderer and drought flag (no live GitHub in pytest)."""

from __future__ import annotations

from daari.gtm.scoreboard import GtmSnapshot, render_scoreboard, viewer_drought


def _snap(**overrides) -> GtmSnapshot:
    base = dict(
        stars=1,
        forks=0,
        unique_viewers_14d=8,
        views_14d=31,
        unique_cloners_14d=133,
        clones_14d=593,
        pypi_last_month=230,
        pypi_last_week=19,
        referrers=(("pypi.org", 9), ("github.com", 4)),
        generated_at="2026-08-26T19:00:00Z",
    )
    base.update(overrides)
    return GtmSnapshot(**base)


def test_render_scoreboard_includes_core_columns():
    md = render_scoreboard(_snap())
    assert md.startswith("# GTM scoreboard")
    assert "2026-08-26T19:00:00Z" in md
    assert "| Stars | 1 |" in md
    assert "| Unique viewers (14d) | 8 |" in md
    assert "| PyPI downloads (30d) | 230 |" in md
    assert "pypi.org" in md
    assert "github.com" in md
    assert "healthy" in md.lower()
    assert "drought" not in md.lower()


def test_viewer_drought_when_no_unique_viewers():
    dry = _snap(unique_viewers_14d=0, views_14d=0)
    assert viewer_drought(dry) is True
    md = render_scoreboard(dry)
    assert "drought" in md.lower()
    assert viewer_drought(_snap(unique_viewers_14d=1)) is False

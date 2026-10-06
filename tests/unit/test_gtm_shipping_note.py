"""GTM-5: shipping-note drafts from CHANGELOG fixtures."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gtm_shipping_note.py"
_spec = importlib.util.spec_from_file_location("gtm_shipping_note", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
sys.modules["gtm_shipping_note"] = _mod
_spec.loader.exec_module(_mod)
render_shipping_notes = _mod.render_shipping_notes

FIXTURE = """# Changelog

## [Unreleased]

## [1.3.0] — 2026-08-17

**Gateway completeness** — full agent surface.

### License change

- Relicensed to PolyForm Noncommercial

### Gateway

- Responses API for agents
"""


def test_repo_relative_links_become_github_urls():
    """Drafts live under docs/gtm/drafts/; changelog links are repo-root relative.

    MkDocs --strict treats those as doc links and aborts the Pages build.
    """
    changelog = """# Changelog

## [1.4.0] — 2026-09-03

**Shipped.** See [RELEASE-v1.4.0.md](docs/RELEASE-v1.4.0.md).

- Relicensed ([ADR-0016](docs/adr/0016-apache-2-relicense.md), [LICENSE](LICENSE)).
- Already absolute [issue](https://github.com/naveenreddyalka/daari/issues/1).
"""
    notes = render_shipping_notes(changelog)
    blob = "https://github.com/naveenreddyalka/daari/blob/main/"
    assert f"{blob}docs/RELEASE-v1.4.0.md" in notes.markdown
    assert f"{blob}docs/adr/0016-apache-2-relicense.md" in notes.markdown
    assert f"{blob}LICENSE" in notes.markdown
    assert "](docs/" not in notes.markdown
    assert "](LICENSE)" not in notes.markdown
    assert "https://github.com/naveenreddyalka/daari/issues/1" in notes.markdown
    assert "](docs/" not in notes.linkedin
    assert "](LICENSE)" not in notes.linkedin


def test_render_shipping_notes_from_fixture(tmp_path: Path):
    notes = render_shipping_notes(FIXTURE)
    assert "1.3.0" in notes.markdown
    assert "https://naveenreddyalka.github.io/daari/" in notes.markdown
    assert "https://github.com/naveenreddyalka/daari" in notes.markdown
    assert "polyform" in notes.markdown.lower() or "noncommercial" in notes.markdown.lower()
    assert "open-source local" not in notes.markdown.lower()
    assert "Responses API" in notes.markdown
    assert "Gateway completeness — full agent surface." in notes.markdown
    assert "**" not in notes.twitter
    assert len(notes.twitter) < 280
    assert "daari" in notes.linkedin.lower()
    out = tmp_path / "shipping-note.md"
    out.write_text(notes.markdown, encoding="utf-8")
    assert out.stat().st_size > 100

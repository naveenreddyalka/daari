#!/usr/bin/env python3
"""Draft a shipping note from CHANGELOG.md. Never posts anywhere."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = "https://naveenreddyalka.github.io/daari/"
REPO = "https://github.com/naveenreddyalka/daari"
LICENSE_LINE = "Apache 2.0 — OSI open source."


@dataclass(frozen=True)
class ShippingNotes:
    version: str
    markdown: str
    twitter: str
    linkedin: str


_VERSION = re.compile(r"^## \[([^\]]+)\]")


def _latest_release_block(changelog: str) -> tuple[str, str]:
    lines = changelog.splitlines()
    start = None
    version = ""
    for i, line in enumerate(lines):
        match = _VERSION.match(line)
        if not match:
            continue
        name = match.group(1)
        if name.lower() == "unreleased":
            continue
        start = i
        version = name
        break
    if start is None:
        raise ValueError("no released version section in changelog")
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if _VERSION.match(lines[j]):
            end = j
            break
    return version, "\n".join(lines[start:end]).strip()


def _bullets(block: str, limit: int = 6) -> list[str]:
    items = []
    for line in block.splitlines():
        if line.startswith("- "):
            items.append(line[2:].strip())
        if len(items) >= limit:
            break
    return items


def render_shipping_notes(changelog: str) -> ShippingNotes:
    version, block = _latest_release_block(changelog)
    bullets = _bullets(block)
    bullet_md = "\n".join(f"- {b}" for b in bullets) or "- See CHANGELOG.md"
    headline = next(
        (ln[2:].strip() for ln in block.splitlines() if ln.startswith("**")),
        f"daari {version}",
    )
    markdown = f"""# Shipping note — daari {version}

{headline}

{bullet_md}

Docs: {DOCS}
Repo: {REPO}

{LICENSE_LINE}

This file is a draft. A human publishes it. Do not auto-post to HN, Reddit, or X.
"""
    twitter = (
        f"daari {version}: {headline[:120].rstrip('.')} "
        f"{DOCS} ({LICENSE_LINE.split('—')[0].strip()})"
    )[:279]
    linkedin = (
        f"Shipped daari {version}. {headline} "
        f"Install: pip install daari. {DOCS} {LICENSE_LINE}"
    )
    return ShippingNotes(
        version=version, markdown=markdown, twitter=twitter, linkedin=linkedin
    )


def main() -> int:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    notes = render_shipping_notes(text)
    out = ROOT / "docs" / "gtm" / "drafts" / "shipping-note.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        notes.markdown + "\n## X draft\n\n" + notes.twitter + "\n\n## LinkedIn draft\n\n" + notes.linkedin + "\n",
        encoding="utf-8",
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

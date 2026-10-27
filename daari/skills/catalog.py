"""Enumerate ``~/.daari/skills`` for prompt prefix and MCP SEP-2640 (#1965)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class LocalSkill:
    """One flat ``*.md`` skill or AAIF ``*/SKILL.md`` package."""

    id: str
    name: str
    description: str
    body: str
    source: str  # "flat" | "aaif"

    @property
    def uri(self) -> str:
        return f"skill://{self.id}"


_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_DESC_LINE = re.compile(r"(?im)^description:\s*(.+)$")
_HEADING = re.compile(r"(?m)^#\s+(.+)$")


def _description_from_body(body: str, *, fallback: str) -> str:
    match = _FRONT_MATTER.match(body)
    remainder = body
    if match:
        fm = match.group(1)
        desc = _DESC_LINE.search(fm)
        if desc:
            return desc.group(1).strip().strip("\"'")
        remainder = body[match.end() :]
    heading = _HEADING.search(remainder)
    if heading:
        return heading.group(1).strip()
    for line in remainder.splitlines():
        text = line.strip()
        if text:
            return text[:200]
    return fallback


def _read_skill_file(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except Exception:
        return None
    return content or None


def iter_local_skills(*, skills_dir: Path | None = None) -> Iterator[LocalSkill]:
    """Yield flat ``*.md`` then immediate ``*/SKILL.md`` packages (nested ignored)."""
    root = skills_dir if skills_dir is not None else Path.home() / ".daari" / "skills"
    if not root.is_dir():
        return
    for path in sorted(root.glob("*.md")):
        content = _read_skill_file(path)
        if content is None:
            continue
        skill_id = path.stem
        yield LocalSkill(
            id=skill_id,
            name=skill_id,
            description=_description_from_body(content, fallback=skill_id),
            body=content,
            source="flat",
        )
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        skill_md = child / "SKILL.md"
        if not skill_md.is_file():
            continue
        content = _read_skill_file(skill_md)
        if content is None:
            continue
        skill_id = child.name
        yield LocalSkill(
            id=skill_id,
            name=skill_id,
            description=_description_from_body(content, fallback=skill_id),
            body=content,
            source="aaif",
        )


def skills_system_prefix(*, skills_dir: Path | None = None) -> str:
    """Build the system-prompt prefix used by settings (#1937)."""
    sections = [
        f"## Skill: {skill.name}\n{skill.body}" for skill in iter_local_skills(skills_dir=skills_dir)
    ]
    if not sections:
        return ""
    return "# Local daari skills\n\n" + "\n\n".join(sections)


def get_local_skill(skill_id: str, *, skills_dir: Path | None = None) -> LocalSkill | None:
    needle = (skill_id or "").strip()
    if not needle:
        return None
    if needle.startswith("skill://"):
        needle = needle[len("skill://") :]
    for skill in iter_local_skills(skills_dir=skills_dir):
        if skill.id == needle:
            return skill
    return None

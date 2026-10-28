"""Enumerate ``~/.daari/skills`` for prompt prefix and MCP SEP-2640 (#1965, #1979)."""

from __future__ import annotations

import hashlib
import mimetypes
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml


@dataclass(frozen=True)
class LocalSkill:
    """One flat ``*.md`` skill or AAIF ``*/SKILL.md`` package."""

    id: str
    name: str
    description: str
    body: str
    source: str  # "flat" | "aaif"
    frontmatter: dict[str, Any] = field(default_factory=dict)
    # Absolute path to the flat ``*.md`` file, or the AAIF package directory.
    path: Path | None = None

    @property
    def uri(self) -> str:
        """Canonical SEP-2640 SKILL.md resource URI."""
        return f"skill://{self.id}/SKILL.md"

    @property
    def root_uri(self) -> str:
        return f"skill://{self.id}"


_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_DESC_LINE = re.compile(r"(?im)^description:\s*(.+)$")
_HEADING = re.compile(r"(?m)^#\s+(.+)$")


def _parse_frontmatter(body: str, *, skill_id: str, fallback_description: str) -> dict[str, Any]:
    """Return YAML frontmatter as a JSON-ready dict; always include name/description."""
    match = _FRONT_MATTER.match(body)
    parsed: dict[str, Any] = {}
    if match:
        try:
            loaded = yaml.safe_load(match.group(1))
        except yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            parsed = dict(loaded)
    if "name" not in parsed or not str(parsed.get("name") or "").strip():
        parsed["name"] = skill_id
    if "description" not in parsed or not str(parsed.get("description") or "").strip():
        parsed["description"] = fallback_description
    return parsed


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


def _file_digest_and_size(path: Path) -> tuple[str, int]:
    raw = path.read_bytes()
    digest = f"sha256:{hashlib.sha256(raw).hexdigest()}"
    return digest, len(raw)


def _mime_for_path(path: Path) -> str:
    if path.name == "SKILL.md" or path.suffix.lower() in {".md", ".markdown"}:
        return "text/markdown"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def iter_package_files(package_dir: Path) -> Iterator[Path]:
    """Yield every file under an AAIF package (supporting files included)."""
    for path in sorted(package_dir.rglob("*")):
        if path.is_file():
            yield path


def skill_resource_manifest(skill: LocalSkill) -> list[dict[str, Any]]:
    """SEP-2640 ``resources`` array: SKILL.md + every package supporting file."""
    entries: list[dict[str, Any]] = []
    if skill.source == "flat":
        if skill.path is None or not skill.path.is_file():
            return entries
        digest, size = _file_digest_and_size(skill.path)
        entries.append({"uri": skill.uri, "digest": digest, "size": size})
        return entries
    if skill.path is None or not skill.path.is_dir():
        return entries
    for path in iter_package_files(skill.path):
        rel = path.relative_to(skill.path).as_posix()
        digest, size = _file_digest_and_size(path)
        entries.append(
            {
                "uri": f"skill://{skill.id}/{rel}",
                "digest": digest,
                "size": size,
            }
        )
    return entries


def skill_entry_payload(skill: LocalSkill) -> dict[str, Any]:
    """SEP-2640 skill entry shared by ``skills/list`` and ``skills/get``."""
    return {
        "uri": skill.uri,
        "frontmatter": dict(skill.frontmatter),
        "resources": skill_resource_manifest(skill),
    }


def list_skill_resources(skill: LocalSkill) -> list[dict[str, Any]]:
    """``resources/list`` rows for a skill's files (SKILL.md + supporting)."""
    rows: list[dict[str, Any]] = []
    if skill.source == "flat":
        rows.append(
            {
                "uri": skill.uri,
                "name": skill.name,
                "description": skill.description,
                "mimeType": "text/markdown",
            }
        )
        return rows
    if skill.path is None or not skill.path.is_dir():
        return rows
    for path in iter_package_files(skill.path):
        rel = path.relative_to(skill.path).as_posix()
        uri = f"skill://{skill.id}/{rel}"
        name = path.name if rel != "SKILL.md" else skill.name
        desc = skill.description if rel == "SKILL.md" else ""
        rows.append(
            {
                "uri": uri,
                "name": name,
                "description": desc,
                "mimeType": _mime_for_path(path),
            }
        )
    return rows


def read_skill_resource(uri: str, *, skills_dir: Path | None = None) -> dict[str, Any] | None:
    """Resolve ``skill://…`` to a ``resources/read`` contents payload."""
    needle = (uri or "").strip()
    if not needle.startswith("skill://"):
        return None
    rest = needle[len("skill://") :]
    if not rest or rest.endswith("/"):
        return None
    parts = rest.split("/")
    skill_id = parts[0]
    skill = get_local_skill(skill_id, skills_dir=skills_dir)
    if skill is None:
        return None
    # Bare skill root is a directory resource — not readable as file bytes.
    if len(parts) == 1:
        return None
    rel = "/".join(parts[1:])
    if skill.source == "flat":
        if rel != "SKILL.md" or skill.path is None:
            return None
        text = skill.path.read_text(encoding="utf-8")
        return {
            "contents": [
                {
                    "uri": skill.uri,
                    "mimeType": "text/markdown",
                    "text": text,
                }
            ]
        }
    if skill.path is None:
        return None
    target = (skill.path / rel).resolve()
    try:
        target.relative_to(skill.path.resolve())
    except ValueError:
        return None
    if not target.is_file():
        return None
    mime = _mime_for_path(target)
    if mime.startswith("text/") or mime in {"application/json", "application/xml"}:
        text = target.read_text(encoding="utf-8")
        return {
            "contents": [
                {
                    "uri": f"skill://{skill.id}/{rel}",
                    "mimeType": mime,
                    "text": text,
                }
            ]
        }
    import base64

    raw = target.read_bytes()
    return {
        "contents": [
            {
                "uri": f"skill://{skill.id}/{rel}",
                "mimeType": mime,
                "blob": base64.b64encode(raw).decode("ascii"),
            }
        ]
    }


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
        description = _description_from_body(content, fallback=skill_id)
        frontmatter = _parse_frontmatter(
            content, skill_id=skill_id, fallback_description=description
        )
        yield LocalSkill(
            id=skill_id,
            name=str(frontmatter["name"]),
            description=str(frontmatter["description"]),
            body=content,
            source="flat",
            frontmatter=frontmatter,
            path=path,
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
        description = _description_from_body(content, fallback=skill_id)
        frontmatter = _parse_frontmatter(
            content, skill_id=skill_id, fallback_description=description
        )
        # Directory name is the skill name; keep frontmatter.name aligned.
        if str(frontmatter.get("name") or "") != skill_id:
            frontmatter = {**frontmatter, "name": skill_id}
        yield LocalSkill(
            id=skill_id,
            name=skill_id,
            description=str(frontmatter["description"]),
            body=content,
            source="aaif",
            frontmatter=frontmatter,
            path=child,
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
    # Strip /SKILL.md or any supporting path → skill id is the first segment.
    if "/" in needle:
        needle = needle.split("/", 1)[0]
    for skill in iter_local_skills(skills_dir=skills_dir):
        if skill.id == needle:
            return skill
    return None

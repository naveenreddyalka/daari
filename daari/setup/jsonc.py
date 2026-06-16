from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def strip_jsonc(text: str) -> str:
    """Remove // comments and trailing commas so json.loads can parse Cursor settings."""
    without_comments = re.sub(r"//.*?$", "", text, flags=re.MULTILINE)
    return re.sub(r",(\s*[}\]])", r"\1", without_comments)


def load_jsonc(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        loaded = json.loads(strip_jsonc(text))
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return loaded


def dump_jsonc(data: dict[str, Any], *, indent: int = 4) -> str:
    """Write standard JSON (Cursor accepts it on reload)."""
    return json.dumps(data, indent=indent, ensure_ascii=False) + "\n"

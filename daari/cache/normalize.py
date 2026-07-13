"""Embedding input normalization (Trust PRD T1a).

Template-heavy inputs (JSON scaffolding, code fences, repeated boilerplate)
score artificially similar under embedding models — the canonical
semantic-cache false-positive failure mode. Normalizing the *embedded*
text (never the cache key or the stored answer) makes similarity reflect
intent instead of shared template bytes.
"""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"^\s*```[\w-]*\s*$")
# Lines carrying no semantic content: only braces/brackets/punctuation.
_SCAFFOLD_RE = re.compile(r"^[\s{}\[\]()<>,:;\"'`|.=\\/-]*$")
_WS_RE = re.compile(r"\s+")


def normalize_for_embedding(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            continue
        if _SCAFFOLD_RE.match(line):
            continue
        # Strip structural quoting/bracing but keep the words inside.
        lines.append(line.strip().strip("{}[],").strip())
    return _WS_RE.sub(" ", " ".join(lines)).strip()

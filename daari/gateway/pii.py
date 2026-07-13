"""Local PII scrubbing before frontier escalation (Trust PRD T5c).

Regex-based, applied only to the outbound L6 copy of a request — local
processing always sees the original text. A privacy differentiator no
cloud gateway can offer client-side.
"""

from __future__ import annotations

import re

from daari.gateway.internal import Message

# Order matters: SSN and card before phone so digit runs aren't half-eaten.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("card", re.compile(r"\b(?:\d[ -]?){13,16}\b")),
    (
        "phone",
        re.compile(r"\b(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}\b"),
    ),
    ("ip", re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")),
]


def scrub_pii(
    text: str, *, _seen: dict[str, str] | None = None
) -> tuple[str, dict[str, int]]:
    """Replace PII with typed placeholders. Returns (scrubbed, counts by type).

    Identical values map to the same placeholder so cross-references in the
    prompt stay coherent for the model.
    """
    seen = _seen if _seen is not None else {}
    counts: dict[str, int] = {}
    # Resume numbering from placeholders already assigned in earlier messages.
    per_type_next: dict[str, int] = {}
    for placeholder in seen.values():
        kind = placeholder.strip("<>").rsplit("-", 1)[0]
        index = int(placeholder.strip("<>").rsplit("-", 1)[1])
        per_type_next[kind] = max(per_type_next.get(kind, 0), index)

    scrubbed = text
    for kind, pattern in _PATTERNS:
        def _replace(match: re.Match[str], kind: str = kind) -> str:
            value = match.group(0)
            counts[kind] = counts.get(kind, 0) + 1
            if value not in seen:
                per_type_next[kind] = per_type_next.get(kind, 0) + 1
                seen[value] = f"<{kind}-{per_type_next[kind]}>"
            return seen[value]

        scrubbed = pattern.sub(_replace, scrubbed)
    return scrubbed, counts


def scrub_messages(messages: list[Message]) -> tuple[list[Message], dict[str, int]]:
    """Scrub non-system messages; system prompts are the operator's own text."""
    seen: dict[str, str] = {}
    totals: dict[str, int] = {}
    result: list[Message] = []
    for message in messages:
        if message.role == "system" or not message.content:
            result.append(message)
            continue
        scrubbed, counts = scrub_pii(message.content, _seen=seen)
        for kind, count in counts.items():
            totals[kind] = totals.get(kind, 0) + count
        if scrubbed != message.content:
            result.append(message.model_copy(update={"content": scrubbed}))
        else:
            result.append(message)
    return result, totals

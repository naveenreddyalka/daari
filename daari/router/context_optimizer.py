"""Token reduction for local-model requests (docs/prd/intelligence.md Feature 4).

Long client sessions (Cursor especially) resend the full history every turn.
Local models pay for that in context window and latency, so before a local
generation we keep all system messages plus the most recent N non-system
messages, and squeeze redundant whitespace. Agent tool round-trips are never
touched — tool-call pairing must stay intact.
"""

from __future__ import annotations

import re

from daari.gateway.internal import Message

_TRAILING_WS = re.compile(r"[ \t]+(?=\n)")
_BLANK_RUNS = re.compile(r"\n{4,}")


def _squeeze(text: str) -> str:
    text = _TRAILING_WS.sub("", text)
    text = _BLANK_RUNS.sub("\n\n\n", text)
    return text.rstrip()


def optimize_messages(
    messages: list[Message],
    *,
    max_history_messages: int = 20,
    squeeze_whitespace: bool = True,
) -> tuple[list[Message], int, int]:
    """Return (optimized messages, chars_before, chars_after)."""
    chars_before = sum(len(m.content or "") for m in messages)

    non_system_indices = [i for i, m in enumerate(messages) if m.role != "system"]
    drop = set(non_system_indices[:-max_history_messages]) if len(non_system_indices) > max_history_messages else set()

    optimized: list[Message] = []
    for index, message in enumerate(messages):
        if index in drop:
            continue
        if squeeze_whitespace and message.content:
            squeezed = _squeeze(message.content)
            if squeezed != message.content:
                message = message.model_copy(update={"content": squeezed})
        optimized.append(message)

    chars_after = sum(len(m.content or "") for m in optimized)
    return optimized, chars_before, chars_after

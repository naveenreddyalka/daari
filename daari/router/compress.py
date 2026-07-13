"""Frontier context compression (Trust PRD T2c) — LLMLingua-lite.

Before an L6 escalation, long non-system messages are pruned sentence-wise
by embedding relevance to the last user message. Uses the existing Ollama
embedder — no new dependencies. Opt-in via ``frontier.compress_context``.
"""

from __future__ import annotations

import re
from typing import Any

from daari.cache.semantic import cosine_similarity
from daari.gateway.internal import Message

# Messages shorter than this are never worth compressing.
MIN_COMPRESS_CHARS = 600
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _split_sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_RE.split(text) if part.strip()]


async def compress_messages(
    messages: list[Message],
    *,
    embedder: Any,
    target_ratio: float = 0.6,
    min_chars: int = MIN_COMPRESS_CHARS,
) -> tuple[list[Message], int, int]:
    """Return (compressed messages, chars_before, chars_after).

    The last user message is the relevance query and is never modified;
    system messages are never modified (prompt-cache prefix stability).
    On any embedding failure the original messages are returned untouched.
    """
    chars_before = sum(len(m.content or "") for m in messages)

    query_index = next(
        (i for i in range(len(messages) - 1, -1, -1) if messages[i].role == "user"),
        None,
    )
    if query_index is None:
        return messages, chars_before, chars_before

    query_vec = await embedder.embed(messages[query_index].content or "")
    if query_vec is None:
        return messages, chars_before, chars_before

    compressed: list[Message] = []
    for index, message in enumerate(messages):
        content = message.content or ""
        if (
            index == query_index
            or message.role == "system"
            or len(content) < min_chars
        ):
            compressed.append(message)
            continue

        sentences = _split_sentences(content)
        if len(sentences) < 4:
            compressed.append(message)
            continue

        scored: list[tuple[float, int, str]] = []
        failed = False
        for position, sentence in enumerate(sentences):
            vector = await embedder.embed(sentence)
            if vector is None:
                failed = True
                break
            scored.append((cosine_similarity(query_vec, vector), position, sentence))
        if failed:
            compressed.append(message)
            continue

        budget = max(1, int(len(content) * target_ratio))
        kept_positions: set[int] = set()
        used = 0
        for score, position, sentence in sorted(scored, key=lambda item: -item[0]):
            if used >= budget and kept_positions:
                break
            kept_positions.add(position)
            used += len(sentence)

        pruned = " ".join(
            sentence for _, position, sentence in scored if position in kept_positions
        )
        if pruned and len(pruned) < len(content):
            compressed.append(message.model_copy(update={"content": pruned}))
        else:
            compressed.append(message)

    chars_after = sum(len(m.content or "") for m in compressed)
    return compressed, chars_before, chars_after

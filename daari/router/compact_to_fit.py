"""Opt-in history trim before frontier escalate (issue #1340).

When enabled, oversized chat history is reduced to ``max_messages`` /
``max_tokens`` by dropping the oldest *unprotected* turns. System messages,
assistant ``tool_calls`` payloads, and ``tool`` / ``function`` results are
never deleted. If the remainder still exceeds the cap, the request is left
oversized (fail closed) rather than dropping tools.
"""

from __future__ import annotations

from daari.gateway.internal import Message


def _protected(message: Message) -> bool:
    if message.role in {"system", "tool", "function"}:
        return True
    if message.tool_calls:
        return True
    if message.tool_call_id:
        return True
    return False


def estimate_tokens(messages: list[Message]) -> int:
    total = 0
    for message in messages:
        total += max(1, (len(message.content or "") + 3) // 4)
        if message.tool_calls:
            total += max(1, (len(str(message.tool_calls)) + 3) // 4)
    return total


def compact_messages(
    messages: list[Message],
    *,
    enabled: bool = False,
    max_messages: int = 32,
    max_tokens: int = 0,
) -> tuple[list[Message], int, int]:
    """Return (messages, count_before, count_after)."""
    before = len(messages)
    if not enabled:
        return messages, before, before

    def over_budget(kept: list[Message]) -> bool:
        if len(kept) > max_messages:
            return True
        if max_tokens > 0 and estimate_tokens(kept) > max_tokens:
            return True
        return False

    if not over_budget(messages):
        return messages, before, before

    keep = [True] * before
    for index, message in enumerate(messages):
        if not over_budget([m for i, m in enumerate(messages) if keep[i]]):
            break
        if not _protected(message):
            keep[index] = False

    out = [m for i, m in enumerate(messages) if keep[i]]
    return out, before, len(out)

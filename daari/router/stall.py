"""Detect a stuck agent loop from the request's own tool history (#357).

No session store: identical tool calls or a trailing error streak in this
request are enough. Default off; the router bumps one tier when a stall hits.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from typing import Any

from daari.gateway.internal import Message


@dataclass(frozen=True)
class StallMatch:
    pattern: str
    count: int


def detect_stall(
    messages: list[Message],
    *,
    repeats: int = 3,
    window: int = 6,
) -> StallMatch | None:
    """N identical calls in the last `window` calls, or N trailing error results."""
    repeats = max(1, int(repeats))
    window = max(1, int(window))
    calls = _tool_call_signatures(messages)[-window:]
    if calls:
        _sig, count = Counter(calls).most_common(1)[0]
        if count >= repeats:
            return StallMatch(pattern="repeat", count=count)
    errors = _trailing_error_results(messages, limit=window)
    if errors >= repeats:
        return StallMatch(pattern="error_streak", count=errors)
    return None


def bump_tier(tier: str, *, frontier: bool) -> str | None:
    """One step up the ladder, or None if there is nowhere to go."""
    ladder = ["L3", "L4", "L5"]
    if frontier:
        ladder.append("L6")
    if tier not in ladder:
        return None
    index = ladder.index(tier)
    if index + 1 >= len(ladder):
        return None
    return ladder[index + 1]


def _tool_call_signatures(messages: list[Message]) -> list[tuple[str, str]]:
    signatures: list[tuple[str, str]] = []
    for message in messages:
        for call in message.tool_calls or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(function.get("name") or call.get("name") or "").strip()
            if not name:
                continue
            raw = function.get("arguments", call.get("arguments", ""))
            signatures.append((name, _normalize_arguments(raw)))
    return signatures


def _normalize_arguments(raw: Any) -> str:
    parsed: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ""
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            return " ".join(text.split())
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if parsed is None:
        return ""
    return str(parsed)


def _trailing_error_results(messages: list[Message], *, limit: int) -> int:
    """Consecutive error tool results, ignoring the assistant call that invoked them."""
    streak = 0
    seen = 0
    for message in reversed(messages):
        if message.role == "assistant" and message.tool_calls:
            continue
        if message.role != "tool" and not message.tool_call_id:
            if streak:
                break
            continue
        seen += 1
        if seen > limit:
            break
        if not _is_error_result(message.content or ""):
            break
        streak += 1
    return streak


def _is_error_result(content: str) -> bool:
    text = content.strip()
    if not text:
        return False
    if text.startswith("{") or text.startswith("["):
        try:
            parsed = json.loads(text)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, dict):
            flag = parsed.get("isError", parsed.get("is_error"))
            if flag is True:
                return True
            if "error" in parsed and parsed.get("error") not in (None, "", False):
                return True
    lowered = text.lower()
    if lowered.startswith("error") or lowered.startswith("exception"):
        return True
    return text.startswith("Traceback (most recent call last)")

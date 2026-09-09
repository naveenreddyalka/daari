"""Classify an agent turn as explore / implement / verify from tool history (#374).

Stateless: only the request's own tool-call names matter. Default off at the
router; when enabled, explore typically steps one tier down (floor L3).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping

from daari.gateway.internal import Message

PhaseName = str  # "explore" | "implement" | "verify"

_TIER_LADDER = ("L3", "L4", "L5")

_EXPLORE_TOKENS = ("read", "search", "list", "fetch", "grep")
_IMPLEMENT_TOKENS = ("edit", "write", "apply", "replace", "patch")
_VERIFY_TOKENS = ("test", "run", "build", "lint")


@dataclass(frozen=True)
class PhaseMatch:
    phase: PhaseName
    signals: tuple[str, ...]
    counts: Mapping[str, int]


def classify_phase(
    messages: list[Message],
    *,
    window: int = 6,
) -> PhaseMatch | None:
    """Majority phase over the last `window` tool-call names, or None."""
    window = max(1, int(window))
    names = _tool_names(messages)[-window:]
    if not names:
        return None
    phases: list[PhaseName] = []
    signals: list[str] = []
    for name in names:
        phase = _phase_for_name(name)
        if phase is None:
            continue
        phases.append(phase)
        signals.append(name)
    if not phases:
        return None
    counts = Counter(phases)
    # Majority; ties → most recent matching name wins.
    top_count = counts.most_common(1)[0][1]
    tied = {phase for phase, count in counts.items() if count == top_count}
    if len(tied) == 1:
        winner = next(iter(tied))
    else:
        winner = next(phase for phase in reversed(phases) if phase in tied)
    return PhaseMatch(
        phase=winner,
        signals=tuple(signals),
        counts=dict(counts),
    )


def adjust_tier(
    tier: str,
    phase: PhaseName,
    mapping: Mapping[str, int | str],
) -> str:
    """Apply a relative delta or absolute override for `phase`. Floor L3."""
    if tier not in _TIER_LADDER:
        return tier
    raw = mapping.get(phase, 0)
    if isinstance(raw, str):
        absolute = raw.strip().upper()
        if absolute in _TIER_LADDER:
            return absolute
        return tier
    try:
        delta = int(raw)
    except (TypeError, ValueError):
        return tier
    if delta == 0:
        return tier
    index = _TIER_LADDER.index(tier)
    # Floor at L3 (generation ladder); ceiling at L5.
    nxt = max(0, min(len(_TIER_LADDER) - 1, index + delta))
    return _TIER_LADDER[nxt]


def default_phase_map() -> dict[str, int | str]:
    return {"explore": -1, "implement": 0, "verify": 0}


def _tool_names(messages: list[Message]) -> list[str]:
    names: list[str] = []
    for message in messages:
        for call in message.tool_calls or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else {}
            name = str(function.get("name") or call.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _phase_for_name(name: str) -> PhaseName | None:
    lowered = name.lower()
    # Prefer implement/verify tokens before explore so e.g. write_test → implement
    # when both "write" and "test" appear; scan implement, verify, explore.
    for tokens, phase in (
        (_IMPLEMENT_TOKENS, "implement"),
        (_VERIFY_TOKENS, "verify"),
        (_EXPLORE_TOKENS, "explore"),
    ):
        if any(token in lowered for token in tokens):
            return phase
    return None


def resolve_phase_map(settings: Any) -> dict[str, int | str]:
    """Build explore/implement/verify mapping from PhaseRoutingSettings-like object."""
    base = default_phase_map()
    if settings is None:
        return base
    for key in ("explore", "implement", "verify"):
        if hasattr(settings, key):
            base[key] = getattr(settings, key)
        elif isinstance(settings, Mapping) and key in settings:
            base[key] = settings[key]
    return base

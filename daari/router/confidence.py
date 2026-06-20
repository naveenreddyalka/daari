"""Phase A.1 confidence heuristics for local tier results."""

from __future__ import annotations

import re

# Per routing-spec § Confidence scoring — refusal phrases trigger fail.
_REFUSAL_PATTERN = re.compile(r"(?i)(i cannot|i can't|as an ai|i don't have access)")


def score_l3_confidence(content: str) -> float:
    """Score an L3 response for escalation decisions.

    Phase A.1 uses a binary heuristic from routing-spec: pass when response
    length > 10 chars and no refusal phrases. Returns 1.0 (pass) or 0.0 (fail).
    Logprobs and SLM self-eval are deferred to Phase B.
    """
    if len(content.strip()) <= 10:
        return 0.0
    if _REFUSAL_PATTERN.search(content):
        return 0.0
    return 1.0

"""Optional Ollama /v1/systemone difficulty classifier for tier pick (#1292)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from daari.gateway.client_errors import summarize_upstream_failure

COMPLEXITY_TO_TIER = {"trivial": "L3", "standard": "L4", "complex": "L5"}
TIER_LABELS = frozenset({"L3", "L4", "L5"})

_DIFFICULTY_QUESTION = {
    "type": "choice",
    "instructions": "How difficult is this user request to answer well locally?",
    "criteria": {
        "trivial": "Short factual lookup, greeting, or simple rewrite",
        "standard": "Typical coding, summarization, or mid complexity reasoning",
        "complex": "Hard multi-step, large context, architecture, or expert judgment",
    },
}


@dataclass(frozen=True)
class DecisionClassification:
    model: str
    complexity: str
    tier: str
    answer: dict[str, Any]
    usage: dict[str, Any] | None = None


def map_choice_to_complexity(choice: str | None) -> str | None:
    raw = (choice or "").strip().lower()
    if raw in COMPLEXITY_TO_TIER:
        return raw
    upper = (choice or "").strip().upper()
    if upper in TIER_LABELS:
        for complexity, tier in COMPLEXITY_TO_TIER.items():
            if tier == upper:
                return complexity
    return None


def map_score_to_complexity(score: float) -> str:
    if score < 0.34:
        return "trivial"
    if score < 0.67:
        return "standard"
    return "complex"


def classification_from_answers(
    *,
    model: str,
    answers: dict[str, Any],
    usage: dict[str, Any] | None = None,
) -> DecisionClassification | None:
    """Map systemone answers onto complexity + local tier."""
    if not isinstance(answers, dict) or not answers:
        return None
    # Prefer a named difficulty/tier question; else first answer.
    answer = answers.get("difficulty") or answers.get("tier") or next(iter(answers.values()))
    if not isinstance(answer, dict):
        return None
    kind = str(answer.get("type") or "").lower()
    complexity: str | None = None
    if kind == "choice" or "choice" in answer:
        complexity = map_choice_to_complexity(str(answer.get("choice") or ""))
    elif kind == "score" or "score" in answer:
        try:
            complexity = map_score_to_complexity(float(answer.get("score")))
        except (TypeError, ValueError):
            complexity = None
    if complexity is None:
        return None
    return DecisionClassification(
        model=model,
        complexity=complexity,
        tier=COMPLEXITY_TO_TIER[complexity],
        answer=dict(answer),
        usage=dict(usage) if isinstance(usage, dict) else None,
    )


def build_systemone_payload(model: str, state: str) -> dict[str, Any]:
    return {
        "model": model,
        "state": state,
        "questions": {"difficulty": dict(_DIFFICULTY_QUESTION)},
    }


async def classify_via_systemone(
    *,
    base_url: str,
    model: str,
    state: str,
    timeout_seconds: float = 5.0,
    client: httpx.AsyncClient | None = None,
) -> DecisionClassification:
    """POST Ollama /v1/systemone; raises on transport/HTTP/shape errors."""
    url = f"{base_url.rstrip('/')}/v1/systemone"
    payload = build_systemone_payload(model, state)
    owns = client is None
    http = client or httpx.AsyncClient(timeout=timeout_seconds)
    try:
        response = await http.post(url, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        raise RuntimeError(summarize_upstream_failure(exc)) from exc
    finally:
        if owns:
            await http.aclose()
    if not isinstance(data, dict):
        raise RuntimeError("systemone returned non-object JSON")
    answers = data.get("answers")
    if not isinstance(answers, dict):
        raise RuntimeError("systemone response missing answers")
    resolved_model = str(data.get("model") or model)
    result = classification_from_answers(
        model=resolved_model,
        answers=answers,
        usage=data.get("usage") if isinstance(data.get("usage"), dict) else None,
    )
    if result is None:
        raise RuntimeError("systemone answers could not be mapped to a tier")
    return result

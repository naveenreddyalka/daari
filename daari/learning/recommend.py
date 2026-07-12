"""Evidence-based category-policy recommendations (Phase D1b).

Turns FeedbackStore.stats() into a ready-to-paste routing.category_policies
block. Only observed tiers are considered — daari never guesses about a tier
it has no evidence for.
"""

from __future__ import annotations

from typing import Any

# Cheapest first: recommend the least expensive tier that holds up.
TIER_ORDER = ["L3", "L4", "L5"]

DEFAULT_MAX_ESCALATION_RATE = 0.15
DEFAULT_MAX_REJECT_RATE = 0.10


def recommend_policies(
    stats: dict[str, dict[str, dict[str, Any]]],
    *,
    min_samples: int = 20,
    max_escalation_rate: float = DEFAULT_MAX_ESCALATION_RATE,
    max_reject_rate: float = DEFAULT_MAX_REJECT_RATE,
) -> dict[str, dict[str, Any]]:
    recommendations: dict[str, dict[str, Any]] = {}
    for category, tiers in stats.items():
        for tier in TIER_ORDER:
            evidence = tiers.get(tier)
            if evidence is None or evidence["outcomes"] < min_samples:
                continue
            if (
                evidence["escalation_rate"] <= max_escalation_rate
                and evidence["reject_rate"] <= max_reject_rate
            ):
                recommendations[category] = {"tier": tier, "evidence": evidence}
                break
    return recommendations


def recommendation_yaml(recommendations: dict[str, dict[str, Any]]) -> str:
    """Render as a routing.category_policies YAML block with evidence comments."""
    if not recommendations:
        return (
            "# no recommendations — not enough evidence yet.\n"
            "# Keep using daari; rerun once categories have >= min-samples outcomes.\n"
        )
    lines = [
        "# daari learn recommend — evidence-based category policies.",
        "# Paste into ~/.daari/config.yaml (or merge with your existing routing block).",
        "routing:",
        "  category_policies:",
    ]
    for category in sorted(recommendations):
        rec = recommendations[category]
        ev = rec["evidence"]
        lines.append(
            f"    {category}:  # outcomes={ev['outcomes']},"
            f" escalation={ev['escalation_rate'] * 100:.1f}%,"
            f" rejects={ev['reject_rate'] * 100:.1f}%"
        )
        lines.append(f"      tier: {rec['tier']}")
    return "\n".join(lines) + "\n"

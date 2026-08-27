"""Score a routing corpus and fail CI when published floors regress (#173)."""

from __future__ import annotations

import re
from typing import Any

# Phase B exit: $0-tier ≥30%. Live accuracy is 16/19 today; floor is below that.
ZERO_TIER_FLOOR = 0.30
ACCURACY_FLOOR = 0.80


def score_routing_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if row.get("ok") is not None]
    correct = sum(1 for row in scored if row.get("ok"))
    # $0-tier = never left the device: any observed local tier except L6.
    zero = sum(1 for row in scored if row.get("observed") and row["observed"] != "L6")
    accuracy = (correct / len(scored)) if scored else 0.0
    zero_tier_rate = (zero / len(scored)) if scored else 0.0
    return {
        "scored": len(scored),
        "correct": correct,
        "accuracy": accuracy,
        "zero_tier_rate": zero_tier_rate,
    }


def assert_routing_floors(stats: dict[str, Any]) -> None:
    accuracy = float(stats["accuracy"])
    zero = float(stats["zero_tier_rate"])
    if accuracy < ACCURACY_FLOOR:
        raise AssertionError(
            f"accuracy {accuracy:.0%} below CI floor {ACCURACY_FLOOR:.0%}"
        )
    if zero < ZERO_TIER_FLOOR:
        raise AssertionError(
            f"$0-tier {zero:.0%} below CI floor {ZERO_TIER_FLOOR:.0%}"
        )


def parse_published_headline(markdown: str) -> dict[str, Any]:
    zero_match = re.search(r"\$0-tier rate:\*\*\s+(\d+)%", markdown)
    acc_match = re.search(r"Routing accuracy:\*\*\s+(\d+)/(\d+)", markdown)
    if not zero_match or not acc_match:
        raise AssertionError("benchmarks.md headline is missing $0-tier or accuracy")
    correct = int(acc_match.group(1))
    scored = int(acc_match.group(2))
    return {
        "zero_tier_rate": int(zero_match.group(1)) / 100.0,
        "correct": correct,
        "scored": scored,
        "accuracy": (correct / scored) if scored else 0.0,
    }

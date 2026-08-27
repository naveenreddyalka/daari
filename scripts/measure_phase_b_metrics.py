#!/usr/bin/env python3
"""Measure Phase B / #173 routing floors (mocked suite + published live page).

Run: python scripts/measure_phase_b_metrics.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from daari.eval.routing_score import (  # noqa: E402
    ACCURACY_FLOOR,
    ZERO_TIER_FLOOR,
    assert_routing_floors,
    parse_published_headline,
)


def main() -> int:
    page = ROOT / "docs" / "developer" / "resources" / "benchmarks.md"
    stats = parse_published_headline(page.read_text())
    print(f"published: {page}")
    print(f"routing_accuracy: {stats['accuracy']:.1%} ({stats['correct']}/{stats['scored']})")
    print(f"zero_tier_rate_pct: {stats['zero_tier_rate'] * 100:.1f}")
    print(f"floors: accuracy>={ACCURACY_FLOOR:.0%} zero_tier>={ZERO_TIER_FLOOR:.0%}")
    assert_routing_floors(stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

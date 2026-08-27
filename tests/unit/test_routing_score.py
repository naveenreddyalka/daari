"""Routing eval floors for CI (issue #173). No live Ollama."""

from __future__ import annotations

from pathlib import Path

import pytest

from daari.eval.routing_score import (
    ACCURACY_FLOOR,
    ZERO_TIER_FLOOR,
    assert_routing_floors,
    parse_published_headline,
    score_routing_rows,
)

REPO = Path(__file__).resolve().parents[2]


def test_score_routing_rows_computes_rates():
    rows = [
        {"id": "A", "observed": "L3", "ok": True},
        {"id": "B", "observed": "L0", "ok": True},
        {"id": "C", "observed": "L6", "ok": False},
        {"id": "D", "observed": "excluded", "ok": None},
    ]
    stats = score_routing_rows(rows)
    assert stats["scored"] == 3
    assert stats["correct"] == 2
    assert stats["accuracy"] == pytest.approx(2 / 3)
    assert stats["zero_tier_rate"] == pytest.approx(2 / 3)


def test_assert_routing_floors_rejects_regression():
    with pytest.raises(AssertionError, match="accuracy"):
        assert_routing_floors({"accuracy": 0.5, "zero_tier_rate": 1.0})
    with pytest.raises(AssertionError, match="\\$0-tier"):
        assert_routing_floors({"accuracy": 1.0, "zero_tier_rate": 0.1})


def test_published_benchmarks_meet_ci_floors():
    text = (REPO / "docs" / "developer" / "resources" / "benchmarks.md").read_text()
    stats = parse_published_headline(text)
    assert stats["zero_tier_rate"] >= ZERO_TIER_FLOOR
    assert stats["accuracy"] >= ACCURACY_FLOOR
    assert_routing_floors(stats)

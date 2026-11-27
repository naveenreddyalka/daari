"""traces-stats.md documents soft_warnings/rejects cliff maps (#682)."""

from __future__ import annotations

from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "docs/developer/guides/observability/traces-stats.md"


def test_traces_stats_docs_mention_cliff_maps() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "soft_warnings" in text
    assert "rejects" in text
    assert "backend_summary" in text
    assert "metrics-prometheus.md" in text
    assert "regional_processing_applied" in text
    assert "regional_processing_uplift_usd" in text
    assert "daari_regional_processing_uplift_usd_total" in text
    assert "`finish_reason`" in text
    assert "daari_finish_reason_total" in text


def test_traces_stats_docs_mention_frontier_binding_counters() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "`frontier_binding`" in text
    for token in ("signed", "pin_unmatched", "unresolvable"):
        assert token in text
    assert "daari_frontier_binding_total" in text
    assert "`http_5xx_failover`" in text
    assert "daari_http_5xx_failover_total" in text


def test_traces_stats_docs_mention_finish_reason_counters() -> None:
    text = DOC.read_text(encoding="utf-8")
    assert "`finish_reason`" in text
    for token in ("stop", "tool_calls", "length", "pause_turn", "refusal", "other"):
        assert token in text
    assert "max_tokens" in text
    assert "daari_finish_reason_total" in text

"""Thin smoke tests for Auto-mode deepeners (not a full review suite)."""

from __future__ import annotations

from daari.config.persist import persist_safe_config
from daari.learning.propose_defaults import propose_routing_defaults
from daari.enterprise.policy_sync import apply_policy_to_runtime


def test_propose_defaults_writes_yaml(tmp_path):
    path = propose_routing_defaults(
        {
            "by_category": {
                "code": {"accept_rate": 0.95, "n": 100},
                "chat": {"accept_rate": 0.4, "n": 50},
            }
        },
        out_dir=tmp_path,
    )
    text = path.read_text()
    assert "PROPOSAL" in text
    assert "confidence_threshold" in text


def test_persist_safe_config_merges(tmp_path):
    cfg = tmp_path / "config.yaml"
    cfg.write_text("routing:\n  prefer: balanced\n", encoding="utf-8")
    out = persist_safe_config(
        {"routing": {"confidence_threshold": 0.55}, "frontier": {"daily_budget_usd": 1.0}},
        config_path=cfg,
    )
    text = out.read_text()
    assert "confidence_threshold: 0.55" in text
    assert "daily_budget_usd: 1.0" in text
    assert "prefer: balanced" in text


def test_apply_policy_to_runtime():
    class S:
        class routing:
            prefer = "balanced"
            confidence_threshold = 0.7
            latency_budget_ms = 0
            max_tier_for_chat = None

        class frontier:
            daily_budget_usd = 0.0
            monthly_budget_usd = 0.0
            soft_budget_ratio = 0.8
            enabled = False

        class cache:
            class l0:
                ttl_seconds = 0.0

            class l1:
                ttl_seconds = 0.0
                similarity_threshold = 0.88

    class R:
        confidence_threshold = 0.7
        latency_budget_ms = 0
        max_tier_for_chat = None
        model_preference = "balanced"
        frontier_enabled = False
        frontier_daily_budget_usd = 0.0

        class semantic_cache:
            similarity_threshold = 0.88

    applied = apply_policy_to_runtime(
        S,
        R,
        {"routing": {"confidence_threshold": 0.6, "prefer": "latency"}},
    )
    assert R.confidence_threshold == 0.6
    assert R.model_preference == "latency"
    assert "routing.confidence_threshold" in applied

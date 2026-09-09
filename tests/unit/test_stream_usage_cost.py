from types import SimpleNamespace

from daari.gateway.cost_headers import stream_usage_cost
from daari.pricing import cost_usd


def test_local_and_cache_tiers_cost_zero():
    for tier in ("L0", "L1", "L3", "L4", "L5", "Lt", None, ""):
        assert stream_usage_cost(tier=tier, prompt_tokens=100, completion_tokens=20) == 0.0


def test_l6_stream_cost_matches_cost_usd():
    pricing = SimpleNamespace(
        models={"claude-sonnet": SimpleNamespace(input_per_1m=3.0, output_per_1m=15.0)}
    )
    expected = cost_usd(
        "claude-sonnet",
        1000,
        200,
        pricing,
        fallback_per_1k=0.002,
    )
    assert (
        stream_usage_cost(
            tier="L6",
            model="claude-sonnet",
            prompt_tokens=1000,
            completion_tokens=200,
            pricing=pricing,
            fallback_per_1k=0.002,
        )
        == expected
    )
    assert expected > 0


def test_l6_reported_cost_matches_headers():
    assert (
        stream_usage_cost(
            tier="L6",
            model="ignored",
            prompt_tokens=1,
            completion_tokens=1,
            reported_cost=1.25,
        )
        == 1.25
    )

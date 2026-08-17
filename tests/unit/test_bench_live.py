"""Live product benchmark runner (issue #189) — pure-logic tests.

The network paths run only via `python scripts/bench_live.py` (or the
benchmark-marked wrapper) against a live daemon; these tests cover corpus
loading, scoring, pricing, rendering, and the skip path so the default suite
stays green without Ollama.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bench_live.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("bench_live", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_loads_routing_corpus(bench):
    rows = bench.load_jsonl(bench.ROUTING_CORPUS)
    assert len(rows) == 20
    assert rows[0]["id"] == "GP-01"
    assert all("expected_tier_v1" in row for row in rows)


def test_loads_cache_corpus(bench):
    rows = bench.load_jsonl(bench.CACHE_CORPUS)
    assert len(rows) == 36
    labels = {row["label"] for row in rows}
    assert labels == {"paraphrase", "near_miss", "synonym_substitution"}


def test_tier_matches_handles_alternatives(bench):
    assert bench.tier_matches("L3", "L3")
    assert bench.tier_matches("L1", "L1/L3")
    assert bench.tier_matches("L3", "L1/L3")
    assert not bench.tier_matches("L4", "L1/L3")
    assert not bench.tier_matches(None, "L3")


def test_percentile_nearest_rank(bench):
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    assert bench.percentile(values, 50) == 50.0
    assert bench.percentile(values, 95) == 100.0
    assert bench.percentile([42.0], 95) == 42.0


def test_price_usd_uses_direction_rates(bench):
    price = {"input_per_1m": 2.50, "output_per_1m": 10.00}
    # 1M input + 1M output at gpt-4o list rates.
    assert bench.price_usd(1_000_000, 1_000_000, price) == pytest.approx(12.50)
    assert bench.price_usd(1000, 500, price) == pytest.approx(0.0075)


def test_render_markdown_includes_provenance(bench):
    report = {
        "date": "2026-08-17",
        "commit": "abc1234",
        "hardware": "Apple M4 Pro, 48 GB RAM",
        "ollama_version": "0.18.2",
        "models": ["llama3.2:3b"],
        "reference_price_model": "gpt-4o",
        "routing": {
            "total": 20,
            "correct": 17,
            "excluded_frontier": 1,
            "rows": [
                {"id": "GP-01", "expected": "L3", "observed": "L3", "ok": True, "ms": 812.0}
            ],
        },
        "tier_latency": {"L3": {"count": 10, "p50_ms": 800.0, "p95_ms": 1400.0}},
        "zero_cost_rate": 1.0,
        "cache": {
            "l1_enabled": True,
            "retention_total": 18,
            "retention_hits": 15,
            "near_miss_total": 18,
            "near_miss_rejected": 17,
        },
        "usd_avoided": 0.0123,
        "token_note": "provider-reported",
    }
    text = bench.render_markdown(report)
    assert "abc1234" in text
    assert "Apple M4 Pro" in text
    assert "llama3.2:3b" in text
    assert "2026-08-17" in text
    # 1 frontier row excluded from the 20 -> scored denominator is 19.
    assert "17/19" in text
    assert "$0-tier rate" in text


@pytest.mark.benchmark
def test_live_bench_end_to_end(bench, tmp_path):
    """Full run against a live daemon + Ollama; skips (rc 0) when absent."""
    rc = bench.main(["--out", str(tmp_path / "benchmarks.md")])
    assert rc == 0


def test_main_skips_cleanly_when_nothing_listens(bench, capsys):
    # Port 9 (discard) refuses connections immediately on macOS/Linux.
    rc = bench.main(
        [
            "--daemon",
            "http://127.0.0.1:9",
            "--ollama",
            "http://127.0.0.1:9",
            "--no-write",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "SKIP" in out

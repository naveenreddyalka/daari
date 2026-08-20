"""Competitive comparison bench (issue #190) — pure-logic tests.

Same corpus and prompt IDs as the live product bench (#189) so rows join;
three paths: raw Ollama, daari with caches, daari without caches. The network
paths run only against a live daemon; these tests keep the default suite green
without Ollama.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bench_compare.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("bench_compare", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows():
    return [
        {
            "id": "GP-01",
            "raw_ms": 900.0,
            "daari_ms": 850.0,
            "daari_tier": "L3",
            "nocache_ms": 880.0,
            "input_tokens": 100,
            "output_tokens": 50,
            "frontier_usd": 0.00075,
            "daari_usd": 0.0,
        },
        {
            "id": "GP-05",
            "raw_ms": 800.0,
            "daari_ms": 10.0,
            "daari_tier": "L0",
            "nocache_ms": 790.0,
            "input_tokens": 90,
            "output_tokens": 40,
            "frontier_usd": 0.000625,
            "daari_usd": 0.0,
        },
        {
            "id": "GP-08",
            "raw_ms": 5000.0,
            "daari_ms": None,
            "daari_tier": "excluded",
            "nocache_ms": None,
            "input_tokens": None,
            "output_tokens": None,
            "frontier_usd": None,
            "daari_usd": None,
        },
    ]


def test_aggregate_median_speedup_on_cache_hits(bench):
    agg = bench.aggregate_comparison(_rows())
    # GP-05 is the only cache hit: 800ms raw / 10ms daari = 80x.
    assert agg["cache_hit_speedup_median"] == pytest.approx(80.0)
    assert agg["cache_hit_rows"] == 1


def test_aggregate_usd_and_zero_cost(bench):
    agg = bench.aggregate_comparison(_rows())
    assert agg["frontier_usd_total"] == pytest.approx(0.001375)
    assert agg["daari_usd_total"] == 0.0
    # Both served rows stayed local.
    assert agg["zero_cost_rate"] == pytest.approx(1.0)


def test_aggregate_handles_no_cache_hits(bench):
    rows = [r for r in _rows() if r["daari_tier"] != "L0"]
    agg = bench.aggregate_comparison(rows)
    assert agg["cache_hit_rows"] == 0
    assert agg["cache_hit_speedup_median"] is None


def test_render_joins_rows_by_prompt_id(bench):
    report = {
        "date": "2026-08-20",
        "commit": "abc1234",
        "hardware": "Apple M4 Pro, 48 GB RAM",
        "ollama_version": "0.18.2",
        "raw_model": "llama3.2:3b",
        "reference_price_model": "gpt-4o",
        "rows": _rows(),
        **bench.aggregate_comparison(_rows()),
    }
    text = bench.render_markdown(report)
    assert "GP-01" in text and "GP-05" in text and "GP-08" in text
    assert "abc1234" in text
    assert "llama3.2:3b" in text
    # Frontier column must be labeled as priced, not measured.
    assert "priced" in text.lower() or "implied" in text.lower()
    assert "80" in text  # the speedup aggregate


def test_main_skips_cleanly_without_ollama(bench, capsys):
    rc = bench.main(["--ollama", "http://127.0.0.1:9", "--no-write"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out


@pytest.mark.benchmark
def test_live_comparison_end_to_end(bench, tmp_path):
    rc = bench.main(["--out", str(tmp_path / "comparison.md")])
    assert rc == 0

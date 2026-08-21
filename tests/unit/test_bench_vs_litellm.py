"""daari vs LiteLLM comparison (issue #214) — pure-logic tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bench_vs_litellm.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("bench_vs_litellm", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rows():
    return [
        {
            "id": "GP-01",
            "litellm_ms": 900.0,
            "daari_ms": 850.0,
            "daari_tier": "L3",
            "frontier_usd": 0.00075,
        },
        {
            "id": "GP-05",
            "litellm_ms": 800.0,
            "daari_ms": 10.0,
            "daari_tier": "L0",
            "frontier_usd": 0.000625,
        },
        {
            "id": "GP-08",
            "litellm_ms": 5000.0,
            "daari_ms": None,
            "daari_tier": "excluded",
            "frontier_usd": None,
        },
    ]


def test_aggregate_ratios(bench):
    agg = bench.aggregate(_rows())
    # All served: 900/850 and 800/10 → median of 1.06 and 80.
    assert agg["served"] == 2
    assert agg["cache_hit_rows"] == 1
    assert agg["cache_hit_speedup_median"] == pytest.approx(80.0)
    assert agg["overall_speedup_median"] == pytest.approx((900 / 850 + 80) / 2, rel=0.01)
    assert agg["frontier_usd_total"] == pytest.approx(0.001375)
    assert agg["zero_cost_rate"] == pytest.approx(1.0)


def test_render_joins_by_prompt_id(bench):
    report = {
        "date": "2026-08-21",
        "commit": "abc1234",
        "hardware": "Apple M4 Pro, 48 GB RAM",
        "ollama_version": "0.18.2",
        "model": "llama3.2:3b",
        "litellm_version": "1.2.3",
        "rows": _rows(),
        **bench.aggregate(_rows()),
    }
    text = bench.render_markdown(report)
    assert "GP-01" in text and "GP-05" in text and "GP-08" in text
    assert "LiteLLM" in text
    assert "abc1234" in text
    assert "priced" in text.lower() or "implied" in text.lower()


def test_main_skips_without_ollama(bench, capsys):
    rc = bench.main(["--ollama", "http://127.0.0.1:9", "--no-write"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out


def test_main_skips_without_litellm_when_unspawnable(bench, capsys, monkeypatch):
    monkeypatch.setattr(bench, "litellm_available", lambda: False)
    monkeypatch.setattr(bench, "ollama_version", lambda _url: "0.18.2")
    rc = bench.main(["--no-spawn", "--no-write"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out


@pytest.mark.benchmark
def test_live_vs_litellm_end_to_end(bench, tmp_path):
    rc = bench.main(["--out", str(tmp_path / "vs-litellm.md")])
    assert rc == 0

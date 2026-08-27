"""Load harness (issue #215) — reporter and skip path only."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bench_load.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("bench_load", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_named_mixes_exist(bench):
    assert set(bench.MIXES) >= {"cache", "generate", "agent"}


def test_cache_seeds_are_l3_questions(bench):
    assert len(bench.CACHE_SEEDS) >= 8
    assert all(len(prompt) > 20 and "?" in prompt for prompt in bench.CACHE_SEEDS)
    assert all("load-cache-warm" not in prompt for prompt in bench.CACHE_SEEDS)


def test_agent_tools_are_openai_functions(bench):
    assert bench.AGENT_TOOLS
    function = bench.AGENT_TOOLS[0]["function"]
    assert function["name"]
    assert "parameters" in function


def test_replay_from_probes_drops_unseedable(bench):
    seeds = ["a?", "b?", "c?"]
    assert bench.replay_from_probes(seeds, [True, False, True]) == ["a?", "c?"]
    assert bench.replay_from_probes(seeds, [False, False, False]) == []


def test_summarize_latency_and_rps(bench):
    samples = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    stats = bench.summarize(samples, errors=1, elapsed_s=2.0, concurrency=4, cache_hits=9)
    assert stats["count"] == 10
    assert stats["errors"] == 1
    assert stats["error_rate"] == pytest.approx(1 / 11)
    assert stats["p50_ms"] == 50.0
    assert stats["p95_ms"] == 100.0
    assert stats["rps"] == pytest.approx(5.0)
    assert stats["concurrency"] == 4
    assert stats["cache_hit_rate"] == pytest.approx(9 / 10)


def test_summarize_empty(bench):
    stats = bench.summarize([], errors=3, elapsed_s=0.0, concurrency=2)
    assert stats["rps"] == 0.0
    assert stats["error_rate"] == 1.0


def test_render_includes_provenance(bench):
    report = {
        "date": "2026-08-25",
        "commit": "abc1234",
        "hardware": "Apple M4 Pro, 48 GB RAM",
        "ollama_version": "0.18.2",
        "mixes": {
            "cache": {
                "count": 200,
                "errors": 0,
                "error_rate": 0.0,
                "p50_ms": 8.0,
                "p95_ms": 14.0,
                "rps": 92.4,
                "concurrency": 16,
                "cache_hit_rate": 1.0,
            },
            "generate": {
                "count": 20,
                "errors": 1,
                "error_rate": 0.05,
                "p50_ms": 1400.0,
                "p95_ms": 3100.0,
                "rps": 1.8,
                "concurrency": 2,
            },
            "agent": {
                "count": 80,
                "errors": 0,
                "error_rate": 0.0,
                "p50_ms": 12.0,
                "p95_ms": 22.0,
                "rps": 140.0,
                "concurrency": 8,
                "cache_hit_rate": 1.0,
                "prompt_tokens": 12000,
                "frontier_usd_avoided": 0.03,
            },
        },
    }
    text = bench.render_markdown(report)
    assert "abc1234" in text
    assert "Apple M4 Pro" in text
    assert "92.4" in text
    assert "16" in text
    assert "100%" in text or "1.00" in text
    assert "cache" in text.lower()
    assert "generate" in text.lower()
    assert "agent" in text.lower()
    assert "140.0" in text
    assert "0.03" in text or "$0.03" in text


def test_main_skips_without_ollama(bench, capsys):
    rc = bench.main(["--ollama", "http://127.0.0.1:9", "--no-write"])
    assert rc == 0
    assert "SKIP" in capsys.readouterr().out


@pytest.mark.benchmark
def test_live_load_end_to_end(bench, tmp_path):
    rc = bench.main(
        [
            "--out",
            str(tmp_path / "load.md"),
            "--cache-requests",
            "8",
            "--generate-requests",
            "2",
            "--agent-requests",
            "8",
        ]
    )
    assert rc == 0

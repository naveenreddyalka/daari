"""Competitive comparison bench: daari vs raw Ollama vs frontier price (issue #190).

Runs the same labeled prompt set as the live product bench (#189) three ways
on the same machine, so rows join by prompt ID:

1. raw Ollama — the model daari's L3 tier uses, called directly
2. daari with caches on — a hermetic cold `daari serve`, prompts in corpus order
3. daari with caches off — same daemon, `X-Daari-No-Cache` per request

The frontier column is a *price*, not a call: gpt-4o list rates applied to the
token counts daari recorded, labeled as such. The default run never calls a
paid API; `--live-frontier` opts in to scoring expected-L6 rows for real.

Run: python scripts/bench_compare.py
Writes docs/developer/resources/benchmark-comparison.md; skips cleanly when
Ollama is unreachable.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "docs" / "developer" / "resources" / "benchmark-comparison.md"

_spec = importlib.util.spec_from_file_location("bench_live", REPO / "scripts" / "bench_live.py")
bench_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench_live)

CACHE_TIERS = {"L0", "L1", "L1-org"}


def raw_ollama_chat(ollama: str, model: str, prompt: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{ollama}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        response.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "ms": (time.perf_counter() - started) * 1000}
    return {"ok": True, "ms": (time.perf_counter() - started) * 1000}


def run_comparison(
    ollama: str,
    raw_model: str,
    price: dict[str, float],
    timeout: float,
    allow_frontier: bool,
) -> list[dict[str, Any]]:
    corpus = bench_live.load_jsonl(bench_live.ROUTING_CORPUS)

    print("path 1/3: raw Ollama ...", flush=True)
    raw_ms: dict[str, float | None] = {}
    for row in corpus:
        result = raw_ollama_chat(ollama, raw_model, row["prompt"], timeout)
        raw_ms[row["id"]] = result["ms"] if result["ok"] else None

    daemon = bench_live.HermeticDaemon(ollama)
    if not daemon.wait_ready():
        daemon.stop()
        raise RuntimeError("hermetic daari serve failed to start")
    client = bench_live.BenchClient(daemon.url, "", timeout, allow_frontier)
    rows: list[dict[str, Any]] = []
    try:
        print("path 2/3: daari, caches on ...", flush=True)
        daari: dict[str, dict[str, Any]] = {}
        for row in corpus:
            if "L6" in row["expected_tier_v1"].split("/") and not allow_frontier:
                daari[row["id"]] = {"excluded": True}
                continue
            daari[row["id"]] = client.chat(row["prompt"])

        print("path 3/3: daari, caches off ...", flush=True)
        for row in corpus:
            rid = row["id"]
            record = daari[rid]
            if record.get("excluded"):
                rows.append(
                    {
                        "id": rid,
                        "raw_ms": raw_ms[rid],
                        "daari_ms": None,
                        "daari_tier": "excluded",
                        "nocache_ms": None,
                        "input_tokens": None,
                        "output_tokens": None,
                        "frontier_usd": None,
                        "daari_usd": None,
                    }
                )
                continue
            nocache = client.chat(row["prompt"], extra_headers={"X-Daari-No-Cache": "true"})
            served = record.get("ok", False)
            if served and (record.get("usage_estimated") or record.get("input_tokens") is None):
                input_tokens = max(1, record.get("prompt_chars", 0) // 4)
                output_tokens = max(0, record.get("content_chars", 0) // 4)
            elif served:
                input_tokens = int(record["input_tokens"])
                output_tokens = int(record.get("output_tokens") or 0)
            else:
                input_tokens = output_tokens = None
            rows.append(
                {
                    "id": rid,
                    "raw_ms": raw_ms[rid],
                    "daari_ms": record["ms"] if served else None,
                    "daari_tier": record.get("tier") or "error",
                    "nocache_ms": nocache["ms"] if nocache.get("ok") else None,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "frontier_usd": (
                        bench_live.price_usd(input_tokens, output_tokens, price)
                        if served
                        else None
                    ),
                    # Local tiers cost nothing; an L6 row would carry a real
                    # provider bill that the ledger owns, not this bench.
                    "daari_usd": (0.0 if served and record.get("tier") != "L6" else None),
                }
            )
    finally:
        daemon.stop()
    return rows


def aggregate_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    speedups = [
        row["raw_ms"] / row["daari_ms"]
        for row in rows
        if row["daari_tier"] in CACHE_TIERS
        and row["raw_ms"] is not None
        and row["daari_ms"]
    ]
    served = [row for row in rows if row["daari_ms"] is not None]
    zero_cost = [row for row in served if row["daari_tier"] != "L6"]
    return {
        "cache_hit_rows": len(speedups),
        "cache_hit_speedup_median": statistics.median(speedups) if speedups else None,
        "frontier_usd_total": sum(row["frontier_usd"] or 0.0 for row in rows),
        "daari_usd_total": sum(row["daari_usd"] or 0.0 for row in rows),
        "zero_cost_rate": (len(zero_cost) / len(served)) if served else 0.0,
    }


def _ms(value: float | None) -> str:
    return f"{value:.0f}" if value is not None else "—"


def _usd(value: float | None) -> str:
    return f"${value:.5f}" if value is not None else "—"


def render_markdown(report: dict[str, Any]) -> str:
    speedup = report["cache_hit_speedup_median"]
    lines = [
        "# Benchmark: daari vs raw Ollama vs frontier price",
        "",
        "Generated by `python scripts/bench_compare.py`. Same prompt IDs as the",
        "[live product benchmark](benchmarks.md), so rows join across the two",
        "pages. The frontier column is gpt-4o list rates **priced** onto the",
        "token counts daari recorded — no paid API is called.",
        "",
        f"- **Date:** {report['date']}",
        f"- **Commit:** `{report['commit']}`",
        f"- **Hardware:** {report['hardware']}",
        f"- **Ollama:** {report['ollama_version']} (raw path model: {report['raw_model']})",
        f"- **Reference frontier price:** {report['reference_price_model']} list rates",
        "",
        "## Aggregate",
        "",
        f"- **$0-tier rate:** {report['zero_cost_rate']:.0%} of served requests",
        (
            f"- **Median speedup on cache hits:** {speedup:.0f}x over raw Ollama"
            f" ({report['cache_hit_rows']} hit row(s) in a single cold pass)"
            if speedup is not None
            else "- **Median speedup on cache hits:** n/a — no cache hits this pass"
        ),
        f"- **Implied frontier spend for this corpus:** {_usd(report['frontier_usd_total'])} (priced, not billed)",
        f"- **daari spend:** {_usd(report['daari_usd_total'])}",
        "",
        "## Per-prompt comparison",
        "",
        "| ID | raw Ollama ms | daari ms | daari tier | daari no-cache ms | implied frontier USD | daari USD |",
        "|----|---------------|----------|------------|-------------------|----------------------|-----------|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['id']} | {_ms(row['raw_ms'])} | {_ms(row['daari_ms'])} "
            f"| {row['daari_tier']} | {_ms(row['nocache_ms'])} "
            f"| {_usd(row['frontier_usd'])} | {_usd(row['daari_usd'])} |"
        )
    lines += [
        "",
        "Rows marked `excluded` expect the frontier tier; the default run never",
        "calls a paid API (`--live-frontier` opts in).",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    parser.add_argument("--raw-model", default="llama3.2:3b")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--price-model", default="gpt-4o")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--live-frontier", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    try:
        ollama_version = httpx.get(f"{args.ollama}/api/version", timeout=5).json()["version"]
    except Exception as exc:
        print(f"SKIP: Ollama unreachable at {args.ollama} ({exc})")
        return 0

    price = bench_live.reference_price(args.price_model)
    try:
        rows = run_comparison(args.ollama, args.raw_model, price, args.timeout, args.live_frontier)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    report = {
        "date": time.strftime("%Y-%m-%d"),
        "commit": bench_live.git_commit(),
        "hardware": bench_live.hardware_summary(),
        "ollama_version": ollama_version,
        "raw_model": args.raw_model,
        "reference_price_model": args.price_model,
        "rows": rows,
        **aggregate_comparison(rows),
    }
    text = render_markdown(report)
    print(text)
    if not args.no_write:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

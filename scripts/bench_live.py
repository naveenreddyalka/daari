"""Live product benchmark against a real daari daemon + Ollama (issue #189).

Talks to `daari serve` the way a client would — no stubbed executors — using
the labeled corpora in `evals/routing/prompts.jsonl` and
`evals/cache/verification.jsonl`. Reports $0-tier rate, routing accuracy,
L1 paraphrase-retention / near-miss rejection, p50/p95 latency per tier, and
frontier USD avoided from provider-reported tokens, then writes
`docs/developer/resources/benchmarks.md` with commit, hardware, model IDs,
and date.

Run: python scripts/bench_live.py

By default the script spawns its own hermetic `daari serve` (temp HOME, cold
caches, default settings) so numbers are reproducible and the long-lived
daemon's caches neither pollute nor get polluted by the run. Pass
`--daemon URL` to benchmark an existing daemon instead (its warm caches will
color the results).

Skips cleanly (exit 0) when Ollama is unreachable. Never calls a paid API by
default: every request carries X-Daari-No-Frontier, and rows whose expected
tier is L6 are excluded from accuracy unless --allow-frontier.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]
ROUTING_CORPUS = REPO / "evals" / "routing" / "prompts.jsonl"
CACHE_CORPUS = REPO / "evals" / "cache" / "verification.jsonl"
DEFAULT_OUT = REPO / "docs" / "developer" / "resources" / "benchmarks.md"

RETAIN_LABELS = {"paraphrase", "synonym_substitution"}


class SkipBench(Exception):
    """A dependency is absent; the bench should exit 0 without results."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def tier_matches(observed: str | None, expected: str) -> bool:
    if not observed:
        return False
    return observed in expected.split("/")


def percentile(values: list[float], pct: int) -> float:
    """Nearest-rank percentile; values need not be sorted."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil without math
    return ordered[rank - 1]


def price_usd(input_tokens: int, output_tokens: int, price: dict[str, float]) -> float:
    return (
        input_tokens * price["input_per_1m"] + output_tokens * price["output_per_1m"]
    ) / 1_000_000


def reference_price(model: str) -> dict[str, float]:
    from daari.config.settings import PricingSettings

    entry = PricingSettings().models[model]
    return {"input_per_1m": entry.input_per_1m, "output_per_1m": entry.output_per_1m}


def hardware_summary() -> str:
    if sys.platform == "darwin":
        try:
            cpu = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip()
            mem_bytes = int(
                subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
            )
            return f"{cpu}, {mem_bytes // (1024**3)} GB RAM"
        except Exception:
            pass
    return f"{platform.processor() or platform.machine()}, {os.cpu_count()} cores"


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class HermeticDaemon:
    """A cold `daari serve` in a temp HOME so caches start empty."""

    def __init__(self, ollama: str):
        self._home = tempfile.TemporaryDirectory(prefix="daari-bench-")
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        env = dict(os.environ)
        env["HOME"] = self._home.name
        env["OLLAMA_HOST"] = ollama
        self._log = open(Path(self._home.name) / "serve.log", "w")
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "daari", "serve", "--host", "127.0.0.1", "--port", str(self.port)],
            env=env,
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )

    def wait_ready(self, timeout: float = 45.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                return False
            try:
                if httpx.get(f"{self.url}/health", timeout=2).status_code == 200:
                    return True
            except Exception:
                time.sleep(0.5)
        return False

    def stop(self) -> None:
        self._proc.terminate()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._log.close()
        self._home.cleanup()


class BenchClient:
    def __init__(self, daemon: str, api_key: str, timeout: float, allow_frontier: bool):
        headers = {"X-Daari-Meta": "true", "X-Daari-Client-Id": "bench-live"}
        if not allow_frontier:
            headers["X-Daari-No-Frontier"] = "true"
        if api_key:
            headers["x-api-key"] = api_key
        self._client = httpx.Client(base_url=daemon, headers=headers, timeout=timeout)

    def chat(self, prompt: str, *, extra_headers: dict[str, str] | None = None) -> dict[str, Any]:
        payload = {
            "model": "daari",
            "messages": [{"role": "user", "content": prompt}],
        }
        started = time.perf_counter()
        try:
            response = self._client.post(
                "/v1/chat/completions", json=payload, headers=extra_headers or {}
            )
            elapsed_ms = (time.perf_counter() - started) * 1000
            body = response.json()
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200], "ms": (time.perf_counter() - started) * 1000}
        meta = body.get("daari_meta") or {}
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        return {
            "ok": response.status_code == 200,
            "status": response.status_code,
            "ms": elapsed_ms,
            "tier": meta.get("tier"),
            "model": meta.get("model"),
            "cache_hit": bool(meta.get("cache_hit")),
            "escalated_from": meta.get("escalated_from"),
            "input_tokens": meta.get("input_tokens"),
            "output_tokens": meta.get("output_tokens"),
            "usage_estimated": meta.get("usage_estimated", True),
            "prompt_chars": len(prompt),
            "content_chars": len(content or ""),
        }


def run_routing(client: BenchClient, allow_frontier: bool) -> dict[str, Any]:
    rows_out = []
    correct = 0
    scored = 0
    excluded = 0
    for row in load_jsonl(ROUTING_CORPUS):
        expected = row["expected_tier_v1"]
        if "L6" in expected.split("/") and not allow_frontier:
            excluded += 1
            rows_out.append(
                {"id": row["id"], "expected": expected, "observed": "excluded", "ok": None, "ms": 0.0}
            )
            continue
        result = client.chat(row["prompt"])
        ok = result.get("ok", False) and tier_matches(result.get("tier"), expected)
        scored += 1
        correct += 1 if ok else 0
        rows_out.append(
            {
                "id": row["id"],
                "expected": expected,
                "observed": result.get("tier") or result.get("error", "error"),
                "ok": ok,
                "ms": result.get("ms", 0.0),
                "_raw": result,
            }
        )
    return {
        "total": len(rows_out),
        "scored": scored,
        "correct": correct,
        "excluded_frontier": excluded,
        "rows": rows_out,
    }


def run_cache_trust(client: BenchClient, *, salt_pairs: bool) -> dict[str, Any]:
    """Seed each stored prompt organically, then measure the candidate's L1 outcome.

    paraphrase / synonym_substitution candidates should hit (retention);
    near_miss candidates must not (rejection). Seeds must NOT use
    X-Daari-Tier-Override: the override becomes part of the L1 context key, so
    overridden entries live in a bucket organic requests never read. Pairs
    whose seed lands on a non-cacheable tier (L2/Lt/CCS) are excluded and
    counted. On a warm external daemon the pairs are salted to reduce
    interference from earlier runs; the hermetic default needs no salt.
    """
    retention_total = retention_hits = 0
    near_total = near_hits = 0
    unseedable = 0
    for row in load_jsonl(CACHE_CORPUS):
        suffix = f" [ctx {uuid.uuid4().hex[:8]}]" if salt_pairs else ""
        seeded = client.chat(f"{row['stored']}{suffix}")
        # L1 stores only generated answers (L3/L4/L5); an L1 seed response
        # means a semantically equivalent entry already exists, which seeds
        # the pair just as well.
        if not seeded.get("ok") or seeded.get("tier") not in {"L1", "L3", "L4", "L5"}:
            unseedable += 1
            continue
        result = client.chat(f"{row['candidate']}{suffix}")
        hit = result.get("ok") and result.get("cache_hit") and result.get("tier") == "L1"
        if row["label"] in RETAIN_LABELS:
            retention_total += 1
            retention_hits += 1 if hit else 0
        else:
            near_total += 1
            near_hits += 1 if hit else 0
    return {
        "retention_total": retention_total,
        "retention_hits": retention_hits,
        "near_miss_total": near_total,
        "near_miss_rejected": near_total - near_hits,
        "unseedable": unseedable,
    }


def aggregate(routing: dict[str, Any], price: dict[str, float]) -> dict[str, Any]:
    tier_latency: dict[str, list[float]] = {}
    usd_avoided = 0.0
    zero_cost = 0
    served = 0
    estimated_rows = 0
    models: set[str] = set()
    for row in routing["rows"]:
        raw = row.get("_raw")
        if not raw or not raw.get("ok"):
            continue
        served += 1
        tier = raw.get("tier") or "error"
        tier_latency.setdefault(tier, []).append(raw["ms"])
        if raw.get("model"):
            models.add(raw["model"])
        if tier != "L6":
            zero_cost += 1
            if raw.get("usage_estimated") or raw.get("input_tokens") is None:
                estimated_rows += 1
                input_tokens = max(1, raw.get("prompt_chars", 0) // 4)
                output_tokens = max(0, raw.get("content_chars", 0) // 4)
            else:
                input_tokens = int(raw["input_tokens"])
                output_tokens = int(raw.get("output_tokens") or 0)
            usd_avoided += price_usd(input_tokens, output_tokens, price)
    return {
        "tier_latency": {
            tier: {
                "count": len(values),
                "p50_ms": percentile(values, 50),
                "p95_ms": percentile(values, 95),
            }
            for tier, values in sorted(tier_latency.items())
        },
        "zero_cost_rate": (zero_cost / served) if served else 0.0,
        "usd_avoided": usd_avoided,
        "models": sorted(models),
        "token_note": (
            "provider-reported"
            if estimated_rows == 0
            else f"provider-reported except {estimated_rows} rows estimated at chars/4"
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    routing = report["routing"]
    scored = routing["total"] - routing["excluded_frontier"]
    cache = report["cache"]
    lines = [
        "# Benchmarks",
        "",
        "Generated by `python scripts/bench_live.py` against a live `daari serve`",
        "and real Ollama — no stubbed executors, cold caches. Reproduce on your",
        "machine: [guide](../guides/observability/live-benchmark.md). Historical",
        "notes: [docs/BENCHMARKS.md](../../BENCHMARKS.md).",
        "",
        f"- **Date:** {report['date']}",
        f"- **Commit:** `{report['commit']}`",
        f"- **Hardware:** {report['hardware']}",
        f"- **Ollama:** {report['ollama_version']}",
        f"- **Daemon:** {report.get('mode', 'hermetic')}",
        f"- **Models observed:** {', '.join(report['models']) or 'n/a'}",
        f"- **Reference frontier price:** {report['reference_price_model']} list rates",
        f"- **Token counts:** {report['token_note']}",
        "",
        "## Headline",
        "",
        f"- **$0-tier rate:** {report['zero_cost_rate']:.0%} of served requests never left the machine",
        f"- **Routing accuracy:** {routing['correct']}/{scored} scored rows matched the expected tier"
        + (
            f" ({routing['excluded_frontier']} frontier row(s) excluded — run with --allow-frontier to score them)"
            if routing["excluded_frontier"]
            else ""
        ),
        f"- **Frontier spend avoided:** ${report['usd_avoided']:.4f} for this corpus at {report['reference_price_model']} rates",
    ]
    if cache.get("l1_enabled") is False:
        lines.append("- **L1 cache trust:** skipped — L1 disabled on the daemon")
    else:
        retention = (
            cache["retention_hits"] / cache["retention_total"] if cache["retention_total"] else 0.0
        )
        rejection = (
            cache["near_miss_rejected"] / cache["near_miss_total"] if cache["near_miss_total"] else 0.0
        )
        lines += [
            f"- **L1 paraphrase retention:** {cache['retention_hits']}/{cache['retention_total']} ({retention:.0%})",
            f"- **L1 near-miss rejection:** {cache['near_miss_rejected']}/{cache['near_miss_total']} ({rejection:.0%})",
        ]
        if cache.get("unseedable"):
            lines.append(
                f"- **Cache pairs excluded:** {cache['unseedable']} whose stored prompt "
                "routed to a non-cacheable tier (L2/Lt/CCS)"
            )
    lines += ["", "## Latency per tier", "", "| Tier | Requests | p50 ms | p95 ms |", "|------|----------|--------|--------|"]
    for tier, stats in report["tier_latency"].items():
        lines.append(
            f"| {tier} | {stats['count']} | {stats['p50_ms']:.0f} | {stats['p95_ms']:.0f} |"
        )
    lines += ["", "## Routing corpus detail", "", "| ID | Expected | Observed | OK | ms |", "|----|----------|----------|----|-----|"]
    for row in routing["rows"]:
        ok = {True: "yes", False: "no", None: "—"}[row["ok"]]
        lines.append(
            f"| {row['id']} | {row['expected']} | {row['observed']} | {ok} | {row['ms']:.0f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--daemon",
        default=None,
        help="Benchmark an existing daemon instead of spawning a hermetic one.",
    )
    parser.add_argument("--ollama", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--price-model", default="gpt-4o")
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--allow-frontier", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    try:
        ollama_version = httpx.get(f"{args.ollama}/api/version", timeout=5).json()["version"]
    except Exception as exc:
        print(f"SKIP: Ollama unreachable at {args.ollama} ({exc})")
        return 0

    api_key = os.environ.get("DAARI_API_KEY", "").strip()
    price = reference_price(args.price_model)

    def client_for_phase() -> tuple[BenchClient, HermeticDaemon | None]:
        """External mode reuses the given daemon; hermetic mode gets a fresh
        cold instance per phase so the routing corpus's L1 entries cannot
        contaminate the cache-trust measurement (and vice versa)."""
        if args.daemon:
            try:
                assert httpx.get(f"{args.daemon}/health", timeout=5).status_code == 200
            except Exception as exc:
                raise SkipBench(f"daemon unreachable at {args.daemon} ({exc})") from exc
            return BenchClient(args.daemon, api_key, args.timeout, args.allow_frontier), None
        daemon = HermeticDaemon(args.ollama)
        if not daemon.wait_ready():
            daemon.stop()
            raise RuntimeError("hermetic daari serve failed to start")
        return BenchClient(daemon.url, api_key, args.timeout, args.allow_frontier), daemon

    mode = (
        f"external ({args.daemon}) — warm caches may color results"
        if args.daemon
        else "hermetic `daari serve` on default settings, cold caches, fresh instance per phase"
    )

    try:
        print(f"routing corpus: {ROUTING_CORPUS.name} ...", flush=True)
        client, daemon = client_for_phase()
        try:
            routing = run_routing(client, args.allow_frontier)
        finally:
            if daemon is not None:
                daemon.stop()
        print(f"  {routing['correct']}/{routing['scored']} scored rows matched", flush=True)

        print(f"cache corpus: {CACHE_CORPUS.name} ...", flush=True)
        client, daemon = client_for_phase()
        try:
            cache = run_cache_trust(client, salt_pairs=bool(args.daemon))
        finally:
            if daemon is not None:
                daemon.stop()
        cache["l1_enabled"] = True
    except SkipBench as skip:
        print(f"SKIP: {skip}")
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1

    agg = aggregate(routing, price)
    report = {
        "date": time.strftime("%Y-%m-%d"),
        "commit": git_commit(),
        "hardware": hardware_summary(),
        "ollama_version": ollama_version,
        "mode": mode,
        "reference_price_model": args.price_model,
        "routing": routing,
        "cache": cache,
        **agg,
    }
    text = render_markdown(report)
    print(text)
    if not args.no_write:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

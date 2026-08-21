"""daari vs LiteLLM on the same Ollama + corpus (issue #214).

Same prompt IDs as #189 / #190 so rows join. LiteLLM is a thin OpenAI-compat
proxy in front of Ollama (default config, no paid providers). daari is a
hermetic cold `daari serve` against the same Ollama.

LiteLLM is not a daari runtime dependency. The script skips if Ollama is
down, or if LiteLLM cannot be reached / spawned. `--spawn` installs the
proxy into a throwaway venv (not the project venv).

Run: python scripts/bench_vs_litellm.py --spawn
Writes docs/developer/resources/benchmark-vs-litellm.md.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import socket
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "docs" / "developer" / "resources" / "benchmark-vs-litellm.md"

_spec = importlib.util.spec_from_file_location("bench_live", REPO / "scripts" / "bench_live.py")
bench_live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench_live)

# Tiers that never call a model. These are the comparison, not L3 vs L3.
FAST_TIERS = {"L0", "L1", "L1-org", "L2", "Lt", "CCS"}


def ollama_version(url: str) -> str:
    return httpx.get(f"{url}/api/version", timeout=5).json()["version"]


def litellm_available() -> bool:
    return shutil.which("litellm") is not None or importlib.util.find_spec("litellm") is not None


def openai_chat(base_url: str, model: str, prompt: str, timeout: float, *, api_key: str = "sk-daari-bench") -> dict[str, Any]:
    started = time.perf_counter()
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            json={"model": model, "messages": [{"role": "user", "content": prompt}]},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        response.raise_for_status()
        response.json()
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200], "ms": (time.perf_counter() - started) * 1000}
    return {"ok": True, "ms": (time.perf_counter() - started) * 1000}


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class LiteLLMProxy:
    """LiteLLM's ollama_chat adapter behind the tiny stdlib shim.

    The official `litellm` proxy extra currently needs Prisma and fights
    FastAPI. The shim is the same adapter the proxy uses, without that stack.
    """

    def __init__(self, ollama: str, model: str, *, python: str | None = None):
        self.port = _free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        self.model = model
        self._home = tempfile.TemporaryDirectory(prefix="daari-litellm-")
        log = open(Path(self._home.name) / "proxy.log", "w")
        self._log = log
        shim = REPO / "scripts" / "_litellm_shim.py"
        self._proc = subprocess.Popen(
            [
                python or sys.executable,
                str(shim),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--model",
                model,
                "--ollama",
                ollama.rstrip("/"),
            ],
            cwd=self._home.name,
            env={**os.environ, "LITELLM_LOCAL_MODEL_COST_MAP": "True"},
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    def wait_ready(self, timeout: float = 45.0) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                return False
            try:
                if httpx.get(f"{self.url}/health", timeout=2).status_code < 500:
                    return True
            except Exception:
                try:
                    if httpx.get(f"{self.url}/v1/models", timeout=2, headers={"Authorization": "Bearer sk-daari-bench"}).status_code < 500:
                        return True
                except Exception:
                    time.sleep(0.4)
        return False

    def stop(self) -> None:
        self._proc.terminate()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()
        self._log.close()
        self._home.cleanup()


def spawn_litellm_venv(ollama: str, model: str) -> tuple[LiteLLMProxy, str]:
    """Install LiteLLM into a throwaway venv and start the proxy."""
    root = tempfile.mkdtemp(prefix="daari-litellm-venv-")
    subprocess.check_call([sys.executable, "-m", "venv", root], stdout=subprocess.DEVNULL)
    python = str(Path(root) / ("Scripts" if os.name == "nt" else "bin") / "python")
    subprocess.check_call(
        [python, "-m", "pip", "install", "--quiet", "--only-binary=:all:", "litellm"],
        stdout=subprocess.DEVNULL,
    )
    version = subprocess.check_output(
        [python, "-c", "from importlib.metadata import version; print(version('litellm'))"],
        text=True,
    ).strip()
    proxy = LiteLLMProxy(ollama, model, python=python)
    if not proxy.wait_ready():
        log_tail = ""
        try:
            log_tail = Path(proxy._home.name).joinpath("proxy.log").read_text()[-800:]
        except Exception:
            pass
        proxy.stop()
        raise RuntimeError(f"LiteLLM proxy failed to start (venv {root}): {log_tail}")
    proxy._venv_root = root  # type: ignore[attr-defined]
    return proxy, version


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    served = [row for row in rows if row["daari_ms"] is not None and row["litellm_ms"]]
    overall = [row["litellm_ms"] / row["daari_ms"] for row in served if row["daari_ms"]]
    hits = [
        row["litellm_ms"] / row["daari_ms"]
        for row in served
        if row["daari_tier"] in FAST_TIERS and row["daari_ms"]
    ]
    zero = [row for row in served if row["daari_tier"] != "L6"]
    return {
        "served": len(served),
        "overall_speedup_median": statistics.median(overall) if overall else None,
        "cache_hit_rows": len(hits),
        "cache_hit_speedup_median": statistics.median(hits) if hits else None,
        "frontier_usd_total": sum(row["frontier_usd"] or 0.0 for row in rows),
        "zero_cost_rate": (len(zero) / len(served)) if served else 0.0,
    }


def _ms(value: float | None) -> str:
    return f"{value:.0f}" if value is not None else "—"


def _usd(value: float | None) -> str:
    return f"${value:.5f}" if value is not None else "—"


def render_markdown(report: dict[str, Any]) -> str:
    overall = report["overall_speedup_median"]
    hit = report["cache_hit_speedup_median"]
    lines = [
        "# Benchmark: daari vs LiteLLM",
        "",
        "Same prompt IDs as the [live product benchmark](benchmarks.md) and the",
        "[Ollama comparison](benchmark-comparison.md). LiteLLM is a default",
        "LiteLLM `ollama_chat` adapter in front of the same local Ollama — no paid",
        "providers. The frontier column is gpt-4o list rates **priced** onto",
        "daari's recorded tokens.",
        "",
        f"- **Date:** {report['date']}",
        f"- **Commit:** `{report['commit']}`",
        f"- **Hardware:** {report['hardware']}",
        f"- **Ollama:** {report['ollama_version']} (model: {report['model']})",
        f"- **LiteLLM:** {report.get('litellm_version') or 'n/a'}",
        "",
        "## Aggregate",
        "",
        f"- **$0-tier rate (daari):** {report['zero_cost_rate']:.0%} of served requests",
        (
            f"- **Median daari speedup vs LiteLLM (all rows):** {overall:.2f}x"
            if overall is not None
            else "- **Median daari speedup vs LiteLLM (all rows):** n/a"
        ),
        (
            f"- **Median speedup on daari cache/rule/tool hits:** {hit:.0f}x"
            f" ({report['cache_hit_rows']} $0-tier row(s))"
            if hit is not None
            else "- **Median speedup on daari cache/rule/tool hits:** n/a"
        ),
        f"- **Implied frontier spend for this corpus:** {_usd(report['frontier_usd_total'])} (priced, not billed)",
        "",
        "## Per-prompt comparison",
        "",
        "| ID | LiteLLM ms | daari ms | daari tier | implied frontier USD |",
        "|----|------------|----------|------------|----------------------|",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['id']} | {_ms(row['litellm_ms'])} | {_ms(row['daari_ms'])} "
            f"| {row['daari_tier']} | {_usd(row['frontier_usd'])} |"
        )
    lines += [
        "",
        "LiteLLM here is the SDK `ollama_chat` adapter (same translation the proxy uses).",
        "daari's wins are the $0 tiers (L0/L1/L2/Lt/CCS),",
        "not a faster llama3.2:3b. Rows marked `excluded` expect frontier.",
        "",
    ]
    return "\n".join(lines)


def run(ollama: str, model: str, litellm_url: str, timeout: float, allow_frontier: bool) -> list[dict[str, Any]]:
    corpus = bench_live.load_jsonl(bench_live.ROUTING_CORPUS)
    print("path 1/2: LiteLLM ...", flush=True)
    lite: dict[str, float | None] = {}
    for row in corpus:
        result = openai_chat(litellm_url, model, row["prompt"], timeout)
        lite[row["id"]] = result["ms"] if result["ok"] else None

    print("path 2/2: daari ...", flush=True)
    daemon = bench_live.HermeticDaemon(ollama)
    if not daemon.wait_ready():
        daemon.stop()
        raise RuntimeError("hermetic daari serve failed to start")
    client = bench_live.BenchClient(daemon.url, "", timeout, allow_frontier)
    price = bench_live.reference_price("gpt-4o")
    rows: list[dict[str, Any]] = []
    try:
        for row in corpus:
            if "L6" in row["expected_tier_v1"].split("/") and not allow_frontier:
                rows.append(
                    {
                        "id": row["id"],
                        "litellm_ms": lite[row["id"]],
                        "daari_ms": None,
                        "daari_tier": "excluded",
                        "frontier_usd": None,
                    }
                )
                continue
            result = client.chat(row["prompt"])
            served = result.get("ok", False)
            if served and (result.get("usage_estimated") or result.get("input_tokens") is None):
                input_tokens = max(1, result.get("prompt_chars", 0) // 4)
                output_tokens = max(0, result.get("content_chars", 0) // 4)
            elif served:
                input_tokens = int(result["input_tokens"])
                output_tokens = int(result.get("output_tokens") or 0)
            else:
                input_tokens = output_tokens = 0
            rows.append(
                {
                    "id": row["id"],
                    "litellm_ms": lite[row["id"]],
                    "daari_ms": result["ms"] if served else None,
                    "daari_tier": result.get("tier") or "error",
                    "frontier_usd": (
                        bench_live.price_usd(input_tokens, output_tokens, price) if served else None
                    ),
                }
            )
    finally:
        daemon.stop()
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ollama", default=os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434"))
    parser.add_argument("--model", default="llama3.2:3b")
    parser.add_argument("--litellm-url", default=os.environ.get("LITELLM_URL"))
    parser.add_argument("--spawn", action="store_true", help="Install LiteLLM in a throwaway venv and start it")
    parser.add_argument("--no-spawn", action="store_true", help="Do not install or start LiteLLM")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--allow-frontier", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    try:
        version = ollama_version(args.ollama)
    except Exception as exc:
        print(f"SKIP: Ollama unreachable at {args.ollama} ({exc})")
        return 0

    proxy: LiteLLMProxy | None = None
    venv_root: str | None = None
    litellm_version = "external"
    litellm_url = args.litellm_url

    try:
        if litellm_url:
            try:
                httpx.get(f"{litellm_url.rstrip('/')}/v1/models", timeout=5)
            except Exception as exc:
                print(f"SKIP: LiteLLM unreachable at {litellm_url} ({exc})")
                return 0
        elif args.no_spawn:
            if not litellm_available():
                print("SKIP: LiteLLM is not installed and --no-spawn was set")
                return 0
            print("SKIP: pass --litellm-url or --spawn to run the comparison")
            return 0
        elif args.spawn or not litellm_available():
            if not args.spawn and not litellm_available():
                print("SKIP: LiteLLM is not installed (rerun with --spawn to use a throwaway venv)")
                return 0
            print("spawning LiteLLM in a throwaway venv ...", flush=True)
            try:
                proxy, litellm_version = spawn_litellm_venv(args.ollama, args.model)
            except Exception as exc:
                print(f"SKIP: could not spawn LiteLLM ({exc})")
                return 0
            litellm_url = proxy.url
            venv_root = getattr(proxy, "_venv_root", None)
        else:
            proxy = LiteLLMProxy(args.ollama, args.model)
            if not proxy.wait_ready():
                proxy.stop()
                print("SKIP: LiteLLM is installed but the proxy failed to start")
                return 0
            litellm_url = proxy.url
            try:
                from importlib.metadata import version as pkg_version

                litellm_version = pkg_version("litellm")
            except Exception:
                litellm_version = "installed"

        assert litellm_url is not None
        rows = run(args.ollama, args.model, litellm_url, args.timeout, args.allow_frontier)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        if proxy is not None:
            proxy.stop()
        if venv_root:
            shutil.rmtree(venv_root, ignore_errors=True)

    report = {
        "date": time.strftime("%Y-%m-%d"),
        "commit": bench_live.git_commit(),
        "hardware": bench_live.hardware_summary(),
        "ollama_version": version,
        "model": args.model,
        "litellm_version": litellm_version,
        "rows": rows,
        **aggregate(rows),
    }
    text = render_markdown(report)
    print(text)
    if not args.no_write:
        Path(args.out).write_text(text)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

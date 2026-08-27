# Live product benchmark

`scripts/bench_live.py` measures daari against a **real local model** the way a
user would — `daari serve` + Ollama, labeled prompts, no stubbed executors —
and publishes the results to
[docs/developer/resources/benchmarks.md](../../resources/benchmarks.md).
It backs the routing-accuracy and cache-trust claims that the mocked CI suite
cannot.

## What it measures

| Metric | Source |
|--------|--------|
| Routing accuracy | `evals/routing/prompts.jsonl` — observed tier vs `expected_tier_v1` (slash-separated alternatives allowed) |
| $0-tier rate | share of served requests answered off-machine-free (any tier except L6) |
| Agent $0-tier rate | `evals/routing/agent.jsonl` posted with a Cursor-shaped `tools` array — share that never left the device |
| Cost of pass | retries each routing row until the expected tier matches, or `--cost-of-pass-cap` (default 3); publishes attempts, ms, and implied $ |
| L1 paraphrase retention | `evals/cache/verification.jsonl` rows labeled `paraphrase` / `synonym_substitution` — candidate should hit L1 |
| L1 near-miss rejection | rows labeled `near_miss` — candidate must **not** hit L1 |
| p50/p95 latency per tier | client-side wall clock per request |
| Frontier spend avoided | provider-reported tokens priced at `pricing.models` list rates (default `gpt-4o`) |

## Reproduce on your machine

```bash
# prerequisites: Ollama running with llama3.2:3b, llama3.1:8b, nomic-embed-text pulled
source .venv/bin/activate
python scripts/bench_live.py
```

The script spawns its own **hermetic `daari serve`** — temp `HOME`, cold
caches, default settings, a fresh instance per phase — so runs are
reproducible and your long-lived daemon's caches neither pollute nor get
polluted by the benchmark. It prints the report and rewrites
`docs/developer/resources/benchmarks.md` with the commit hash, hardware,
model IDs, and date.

The equivalent pytest entry point (used by `pytest -m benchmark`):

```bash
pytest -m benchmark tests/unit/test_bench_live.py
```

Both skip cleanly (exit 0 / pass) when Ollama is unreachable, so CI and
Ollama-less machines are unaffected.

## Flags

| Flag | Meaning |
|------|---------|
| `--daemon URL` | Benchmark an existing daemon instead of spawning a hermetic one. Warm caches will color the results; cache pairs get salted to compensate. |
| `--allow-frontier` | Score expected-L6 rows for real. **Default is never to call a paid API**: every request carries `X-Daari-No-Frontier` and L6 rows are excluded from accuracy. |
| `--price-model NAME` | Reference model from `pricing.models` for the "spend avoided" column (default `gpt-4o`). |
| `--cost-of-pass-cap N` | Retry a missed routing row up to N attempts (default 3). |
| `--ollama URL` | Ollama base URL (default `$OLLAMA_HOST` or `http://127.0.0.1:11434`). |
| `--out PATH` | Where to write the markdown report. |
| `--no-write` | Print the report without touching the docs page. |

## Competitive comparison

`scripts/bench_compare.py` (issue #190) runs the same routing corpus three
ways on the same machine — raw Ollama, daari with caches, daari with
`X-Daari-No-Cache` — and writes
[benchmark-comparison.md](../../resources/benchmark-comparison.md) with
per-prompt latency, tier, and implied frontier cost. Prompt IDs match the
product bench, so rows join across the two pages.

```bash
python scripts/bench_compare.py
```

The frontier column is gpt-4o list rates applied to daari's recorded token
counts, labeled as such — the default run never calls a paid API.
`--live-frontier` opts in to scoring expected-L6 rows for real.

## vs LiteLLM

`scripts/bench_vs_litellm.py` (issue #214) runs the same corpus through
LiteLLM's `ollama_chat` adapter (tiny stdlib shim — the official proxy extra
currently needs Prisma) and a hermetic daari daemon. LiteLLM is not a daari
dependency — `--spawn` installs it into a throwaway venv.

```bash
python scripts/bench_vs_litellm.py --spawn
```

Results: [benchmark-vs-litellm.md](../../resources/benchmark-vs-litellm.md).

## Load

`scripts/bench_load.py` (issues #215, #223) measures achieved RPS and p50/p95
against a hermetic daemon. Three mixes: warmed L0 replay (`cache`), unique
no-cache generations with `max_tokens` capped (`generate`), and a
tool-bearing replay (`agent`) that reports L0 hit rate plus implied
frontier input $ avoided (gpt-4o list rates, priced not billed).

```bash
python scripts/bench_load.py
```

Results: [benchmark-load.md](../../resources/benchmark-load.md). These replace
the estimate-only numbers in the capacity guide. The **agent** row is the
G1 prefix-cache claim: identical Cursor-shaped turns should hit L0.

## Methodology notes

- Seeding for the cache-trust phase is **organic** (plain requests). Do not
  seed with `X-Daari-Tier-Override`: the override becomes part of the L1
  context key, so overridden entries land in a bucket organic lookups never
  read (this is by design — pinned answers must not serve organic traffic).
- Stored prompts that route to a non-cacheable tier (L2/Lt/CCS) cannot seed
  L1; those pairs are excluded and the count is reported.
- Tokens are provider-reported wherever `usage_estimated` is false; the few
  deterministic-tier rows without provider counts are estimated at chars/4 and
  the report says so.

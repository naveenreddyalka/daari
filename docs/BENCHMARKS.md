# Benchmarks

> Measured 2026-07-23 on an Apple Silicon MacBook (M-series), daari v1.2.x, Ollama `llama3.2:3b` as L3.
> Reproduce: `./scripts/bench.sh` against a running daemon (median of 3 runs shown).

## Tier latency (wall clock, localhost)

| Tier | What it does | p50 latency | vs L3 local model |
|------|--------------|------------:|------------------:|
| L0/L1 repeat hit | exact/semantic cache, identical prompt | **~30 ms** | 26× faster |
| L1 semantic hit | paraphrased prompt, embedding match | **~86 ms** | 9× faster |
| L2 rules | deterministic transform (JSON/YAML) | **~30 ms** | 26× faster |
| Lt tool | CLI execution (`git status`) without a model | **~80 ms** | 10× faster |
| L3 local model | `llama3.2:3b` full generation | **~790 ms** | baseline |

Every row above **costs $0** — no tokens leave the machine. A frontier round-trip for the same
prompts is typically 1–4 s network-included, so even the local-model *floor* is competitive,
and cache/rule/tool hits are one to two orders of magnitude faster.

## What that means in money

Cost model used by daari's savings ledger (`daari report`): each request served locally is
priced against what the same tokens would have cost on a frontier model (input + output at
published per-million-token rates, GPT-4o-class default). Illustrative math at 2026 list
prices (~$2.50/M input, ~$10/M output):

| Monthly volume | Typical mix* | Frontier-only cost | With daari | Saved |
|---------------:|--------------|-------------------:|-----------:|------:|
| 10k requests | 35% cache/rules/tools, 55% local, 10% frontier | ~$95 | ~$10 | **~90%** |
| 100k requests | same mix | ~$950 | ~$95 | **~90%** |

*Mix observed on this repo's own development traffic; your `daari report` shows your real
numbers — including the estimated-savings line computed from your actual token counts.

## Cache trust (why the cache rate is believable)

Semantic-cache hits are only savings if they're *correct*. daari shadow-samples a fraction
of L1 hits, re-runs them against the model, and reports a measured **false-hit rate** per
category (`daari report`, `/v1/daari/cache/diversity`). Tune `cache.l1.similarity_threshold`
until the false-hit rate for your workload is acceptable — measured, not vibes.

## Notes

- L3 latency scales with output length; the bench uses short prompts. Longer generations
  favor caches even more.
- The L0 row in `bench.sh` may report `L1` when the semantic cache answers first for the
  repeated prompt — both are ~30 ms cache paths.
- Latency-aware routing (`routing.latency_budget_ms`) steps down to smaller models when a
  profiled model would blow the budget — see `daari profile`.

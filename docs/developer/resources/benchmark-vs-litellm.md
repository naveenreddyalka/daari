# Benchmark: daari vs LiteLLM

Same prompt IDs as the [live product benchmark](benchmarks.md) and the
[Ollama comparison](benchmark-comparison.md). LiteLLM is a default
LiteLLM `ollama_chat` adapter in front of the same local Ollama — no paid
providers. The frontier column is gpt-4o list rates **priced** onto
daari's recorded tokens.

- **Date:** 2026-08-21
- **Commit:** `5740d3b`
- **Hardware:** Apple M4 Pro, 48 GB RAM
- **Ollama:** 0.18.2 (model: llama3.2:3b)
- **LiteLLM:** 1.97.0

## Aggregate

- **$0-tier rate (daari):** 100% of served requests
- **Median daari speedup vs LiteLLM (all rows):** 0.98x
- **Median speedup on daari cache/rule/tool hits:** 27x (5 $0-tier row(s))
- **Implied frontier spend for this corpus:** $0.03480 (priced, not billed)

## Per-prompt comparison

| ID | LiteLLM ms | daari ms | daari tier | implied frontier USD |
|----|------------|----------|------------|----------------------|
| GP-01 | 3725 | 1514 | L3 | $0.00019 |
| GP-02 | 2373 | 2455 | L3 | $0.00221 |
| GP-03 | 806 | 61 | L2 | $0.00009 |
| GP-04 | 372 | 1031 | L3 | $0.00092 |
| GP-05 | 762 | 11 | L0 | $0.00092 |
| GP-06 | 2023 | 76 | Lt | $0.00009 |
| GP-07 | 2690 | 128 | Lt | $0.00168 |
| GP-08 | 10502 | — | excluded | — |
| GP-09 | 1260 | 1908 | L3 | $0.00175 |
| GP-10 | 8413 | 12464 | L3 | $0.01145 |
| GP-11 | 2044 | 2204 | L3 | $0.00194 |
| GP-12 | 1657 | 4340 | L4 | $0.00037 |
| GP-13 | 2685 | 1971 | L3 | $0.00149 |
| GP-14 | 504 | 795 | L3 | $0.00065 |
| GP-15 | 838 | 857 | L3 | $0.00074 |
| GP-16 | 6180 | 1325 | L4 | $0.00069 |
| GP-17 | 374 | 294 | L3 | $0.00015 |
| GP-18 | 3652 | 5735 | L3 | $0.00525 |
| GP-19 | 1939 | 6 | CCS | $0.00009 |
| GP-20 | 4362 | 4500 | L3 | $0.00413 |

LiteLLM here is the SDK `ollama_chat` adapter (same translation the proxy uses).
daari's wins are the $0 tiers (L0/L1/L2/Lt/CCS),
not a faster llama3.2:3b. Rows marked `excluded` expect frontier.

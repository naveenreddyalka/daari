# Boundaries and guardrails

Two different gates that run **before** models spend tokens.

| | **Boundaries** (product scope) | **Guardrails** (safety / abuse) |
|--|-------------------------------|----------------------------------|
| Question | Is this about *our product*? | Is this injection / secret / oversized? |
| Config | `boundaries.*` | `guardrails.*` |
| Clear out | `tier=boundary`, refuse message | `tier=guardrail` |
| Modes | `off` / `warn` / `block` | block / warn / redact |
| ADR | [ADR-0015](../../adr/0015-product-boundaries.md) | ROADMAP F2 |

## Boundaries ladder (local-first)

1. **B0** — topic / example overlap; cosine via the L1 embedder when available
2. **B1** — cheap local judge when ambiguous
3. **B2** — N-vote local quorum (`quorum_votes`) on still-ambiguous cases
4. **B3** — optional frontier judge, hard-capped by `frontier_judge_daily_budget_usd` (off by default; warns at startup if enabled without a frontier)

Start with `mode: warn`, tune topics, then `mode: block`. Example: [`examples/boundaries/fintech-assist.yaml`](https://github.com/naveenreddyalka/daari/blob/main/examples/boundaries/fintech-assist.yaml).

## Next

→ [Boundaries guide](../guides/features/boundaries.md) · [Guardrails guide](../guides/features/guardrails.md)

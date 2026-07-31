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

1. **B0** — topic / example overlap (no model)
2. **B1** — cheap local judge when ambiguous
3. **B2/B3** — quorum / optional frontier judge (off by default)

Start with `mode: warn`, tune topics, then `mode: block`. Example: [`examples/boundaries/fintech-assist.yaml`](https://github.com/naveenreddyalka/daari/blob/main/examples/boundaries/fintech-assist.yaml).

## Next

→ [Boundaries guide](../guides/features/boundaries.md) · [Guardrails guide](../guides/features/guardrails.md)

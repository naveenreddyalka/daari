# ADR-0015: Local-first product boundaries (scope gate)

- **Status:** Accepted
- **Date:** 2026-07-30
- **Context:** [LinkedIn / B2C chatbot scope](https://www.linkedin.com/feed/update/urn:li:ugcPost:7488050105086877696/) — embedded assistants get used as free ChatGPT, burning tokens off-product.

## Decision

Daari enforces an optional **product boundary** *before* L0–L6 routing:

1. **Configurable** — `boundaries.enabled` (default off), `mode: warn|block`, and a full editable definition (product description, allow/deny topics, examples, thresholds, stage toggles) via config.yaml, env, and `PATCH /v1/daari/config`.
2. **Local-first ladder** — B0 topic/example overlap (optional L1-embedder cosine) → B1 cheap local judge on ambiguous → B2 N-vote local quorum → B3 rare frontier judge (off by default; daily USD cap).
3. **Hard refuse** when clearly out and `mode: block` — response `tier=boundary`, zero model tokens.
4. **Warn/dry-run** — classify and attach `daari_meta.boundary` but still answer, to tune false-refuse rate.

## Consequences

- Distinct from F2 regex guardrails (injection/PII) and Lt PolicyEngine (tool allow/deny).
- Org policy sync may push the full `boundaries` blob and rebuild the engine.
- Learning proposals (`propose-boundaries`) stay review-gated; never auto-promote.

## Alternatives rejected

- System-prompt only (“stay on topic”) — models ignore.
- Always-on frontier judge — defeats token savings.
- Regex-only deny lists — too brittle alone (kept as B0 assist).

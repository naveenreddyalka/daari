# Caching and trust

**Outcome:** Know how L0/L1 work and how daari measures whether cache answers are trustworthy.

## L0 — exact

Identical normalized request → stored response. Fastest path. Backend: disk (default) or Redis (`cache.backend: redis`).

## L1 — semantic

Embedding similarity above `cache.l1.similarity_threshold` → reuse. Optional draft injection and shadow sampling for trust.

## Cache trust

Unlike most proxies, daari tracks:

- **False-hit rate** — shadow-sample whether a cache answer would disagree with a fresh model
- **Diversity** — whether a category collapses to one answer
- **Input normalization** — whitespace/punctuation so equivalent prompts share keys

Inspect via `daari report`, web UI cache-trust panel, or `/v1/daari/cache/diversity`.

## Org caches

Optional org service (`daari org-cache serve`) adds L0-org / L1-org after local miss. See [Org cache guide](../guides/features/org-cache.md).

## Knobs

| Key | Meaning |
|-----|---------|
| `cache.l0.enabled` / `cache.l1.enabled` | Toggle tiers |
| `cache.l1.similarity_threshold` | Semantic match bar |
| `cache.backend` | `disk` \| `redis` |
| Header `X-Daari-No-Cache` | Skip cache for one request |

## Next

→ [Measure cache trust tutorial](../tutorials/measure-cache-trust.md) · [Observability](../guides/observability/traces-stats.md)

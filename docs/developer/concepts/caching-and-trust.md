# Caching and trust

**Outcome:** Know how L0/L1 work and how daari measures whether cache answers are trustworthy.

## L0 — exact

Identical normalized request → stored response. Fastest path. Backend: disk (default) or Redis (`cache.backend: redis`).

## L1 — semantic

Embedding similarity above `cache.l1.similarity_threshold` finds a candidate, but
similarity alone does not decide the hit — the candidate must also pass
verification (below). Optional draft injection and shadow sampling add further
trust signals. When `cache.backend: redis`, replica writes use `WATCH`/`MULTI`
so concurrent puts do not clobber each other's entries.

## Verifying a hit before serving it

A cosine threshold cannot separate "how do I list Docker containers?" from "how do
I list Docker *images*?" — those score nearly identically, yet the answers differ.
Raising the threshold to exclude the near-miss also excludes genuine paraphrases,
so a threshold alone trades false hits against hit rate with no good setting.

daari therefore runs a second, cheap check on the nearest candidate and serves it
only if that check agrees. `cache.l1.verify` selects the mode:

| Mode | Behavior |
|------|----------|
| `none` | Serve any candidate above the threshold (pre-verification behavior) |
| `lexical` *(default)* | Reject when numbers, units, negation, or a key content word differ |
| `model` | Lexical checks, then ask a local model to confirm the two prompts are equivalent |

`lexical` costs microseconds and needs no model call, which is why it is the
default. Every rejection is a false hit that would otherwise have been served; it
falls through to normal routing and increments
`daari_cache_false_hits_avoided_total`, also visible as
`cache_false_hits_avoided` in `daari report`.

The rules are pinned by a labeled corpus at `evals/cache/verification.jsonl`,
covering paraphrases that must still hit and near-misses that must not, so tuning
the verifier cannot silently regress either direction.

## Cache trust

Unlike most proxies, daari tracks:

- **False hits avoided** — near-misses rejected by verification before reaching a client
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
| `cache.l1.verify` | Second-stage check: `none` \| `lexical` \| `model` |
| `cache.backend` | `disk` \| `redis` |
| Header `X-Daari-No-Cache` | Skip cache for one request |

## Next

→ [Measure cache trust tutorial](../tutorials/measure-cache-trust.md) · [Observability](../guides/observability/traces-stats.md)

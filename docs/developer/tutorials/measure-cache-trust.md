# Tutorial: Measure cache trust

**Outcome:** Read false-hit and diversity signals for a category.

## Steps

1. Generate traffic that hits L1 (similar prompts).
2. Enable shadow sampling if configured in cache settings.
3. Open web UI or `daari report` — inspect `cache_trust`.
4. `GET /v1/daari/cache/diversity`.

## Verify

Categories show sample counts and false-hit rates; diversity ratio is defined.

## Next

→ [Caching and trust](../concepts/caching-and-trust.md)

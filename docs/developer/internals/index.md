# Internals

For engineers changing daari itself.

## Suggested reading order

1. [What is daari?](../concepts/what-is-daari.md) (product)
2. [Package map](package-map.md)
3. [Request lifecycle](request-lifecycle.md)
4. [Extension points](extension-points.md)
5. [Testing](testing.md)
6. `daari/gateway/internal.py` → `server/app.py` → `gateway/openai.py` → `router/router.py`
7. `tests/integration/test_gateway_flow.py` (if present) / `test_boundaries_gateway.py`

Contributor contract: [AGENTS.md](https://github.com/naveenreddyalka/daari/blob/main/AGENTS.md) · [DEVELOPING.md](../../DEVELOPING.md).

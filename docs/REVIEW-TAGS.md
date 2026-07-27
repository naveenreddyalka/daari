# Fable re-verification tags (post Aug 5)

Commits on backlog work are tagged so a stronger model can re-verify each slice:

| Tag pattern | Meaning |
|-------------|---------|
| `fable-review/135-N-<slug>` | Issue #135 Redis L1 — discrete verification checkpoint |

For each tagged commit, re-run **three** verification approaches:

1. **Unit** — `pytest tests/unit/... -q`
2. **Integration** — `pytest -m integration` and/or gateway ASGI tests
3. **Live/smoke** — hit a running daemon (`/health`, `/v1/chat/completions` or `daari` prompt path)

Do not delete these tags until Fable review is recorded on the linked issue.

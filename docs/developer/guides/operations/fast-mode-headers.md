# Anthropic fast-mode rate-limit headers

**Outcome:** An operator can see when Claude Code, talking to the local
daemon, is looking at Anthropic's dedicated fast-mode token bucket.

When `POST /v1/messages` is served by an Anthropic L6 hop, daari copies these
upstream response headers onto the client response:

- `anthropic-fast-input-tokens-limit`
- `anthropic-fast-input-tokens-remaining`
- `anthropic-fast-input-tokens-reset`
- `anthropic-fast-output-tokens-limit`
- `anthropic-fast-output-tokens-remaining`
- `anthropic-fast-output-tokens-reset`

A header is copied only when that Anthropic L6 response includes it. Headers
the upstream omitted stay absent. No other upstream headers are copied.

Local tiers, cache hits, and a non-Anthropic frontier provider do not add
these headers.

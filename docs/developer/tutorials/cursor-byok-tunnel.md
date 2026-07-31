# Tutorial: Cursor BYOK over a tunnel

**Outcome:** End-to-end Cursor chat through local daari.

## Prerequisites

Ollama + `daari serve`, `cloudflared`.

## Steps

1. `scripts/tunnel.sh --setup-cursor`
2. Ask Cursor: “Say hi in one word.”
3. `daari stats` and confirm a request.
4. Ask the same question again — prefer cache hit when context matches.

## Verify

`daari doctor --tunnel --tunnel-url https://<host>` succeeds; Cursor shows a reply.

## Next

→ [Cursor guide](../guides/clients/cursor.md)

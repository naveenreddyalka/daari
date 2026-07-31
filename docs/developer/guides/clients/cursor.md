# Cursor

**Outcome:** Cursor BYOK sends traffic through daari (via HTTPS tunnel).

## Prerequisites

- `daari serve` running locally
- [`cloudflared`](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) installed (`brew install cloudflared`)

## Steps

Cursor cloud cannot call `127.0.0.1`. Use the tunnel helper:

```bash
scripts/tunnel.sh --setup-cursor
```

This starts daari if needed, opens a Cloudflare quick tunnel, configures Cursor Override OpenAI Base URL, and auto-enables `server.api_key` when unset.

Manual:

```bash
scripts/tunnel.sh
daari setup cursor --base-url "https://<tunnel-host>/v1"
```

## Verify

1. Ask Cursor a short question.
2. `curl -fsS https://<tunnel-host>/health`
3. `daari stats` — request count increases.

## Troubleshoot

| Problem | Fix |
|---------|-----|
| Private networks forbidden | Still on localhost — use tunnel HTTPS URL |
| 401 | Restart daemon after API key generation; Cursor must send the key |
| Empty replies | Check `~/.daari/cursor-requests.log`; restart `daari serve` from venv |
| `cloudflared` missing | `brew install cloudflared` |

Prefer latency? Cap chat at L3 in `~/.daari/config.yaml`:

```yaml
routing:
  max_tier_for_chat: L3
```

## Next

→ [Cursor BYOK tutorial](../../tutorials/cursor-byok-tunnel.md) · [Auth and keys](../configuration/auth-and-keys.md)

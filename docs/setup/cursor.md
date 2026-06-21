# Cursor setup (E2E with tunnel)

## Important: Cursor cannot call localhost directly

Cursor BYOK traffic is proxied through Cursor cloud, so private addresses like `http://127.0.0.1:11435/v1` are blocked (`Access to private networks is forbidden`).  
For Cursor E2E, use an HTTPS tunnel that forwards to local daari.

## Fast path (recommended)

```bash
scripts/tunnel.sh --setup-cursor
```

This command:
- starts `daari serve` if needed
- opens a `cloudflared` quick tunnel to `http://127.0.0.1:11435`
- configures Cursor with the tunnel URL (`https://...trycloudflare.com/v1`)
- keeps running until you stop it (`Ctrl+C`)

Inference still runs locally in daari/Ollama. Only the Cursor HTTP hop is public.

## Manual setup options

### Option A: Use the tunnel script without auto-setup

```bash
scripts/tunnel.sh
```

Then paste the printed URL (`https://.../v1`) into Cursor **Override OpenAI Base URL**.

### Option B: Setup Cursor with explicit base URL

```bash
daari setup cursor --base-url "https://<your-tunnel-host>/v1"
```

### Option C: Let setup command start tunnel

```bash
daari setup cursor --tunnel
```

If `DAARI_TUNNEL_URL` is set, it is used directly.

## Alternatives for true-local E2E (no public tunnel)

- Browser extension: `packages/browser-extension/` (direct localhost usage)
- `curl` against local daemon: `http://127.0.0.1:11435/v1`
- VS Code local setup: `daari setup vscode` (same machine, no Cursor cloud hop)

## Troubleshooting

| Problem | Check |
|---------|-------|
| `Access to private networks is forbidden` | You are still using localhost in Cursor; switch to tunnel HTTPS URL |
| `cloudflared: command not found` | Install: `brew install cloudflared` |
| Tunnel command exits quickly | Inspect tunnel logs in terminal; restart with `scripts/tunnel.sh` |
| Slow every request | Cache miss — verify with `daari stats` |

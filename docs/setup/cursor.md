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

## Securing the tunnel (issue #86)

A public tunnel means anyone with the URL could reach the gateway. Mitigations:

- `daari setup cursor --tunnel` now auto-generates `server.api_key` in
  `~/.daari/config.yaml` (when unset) and configures Cursor to send it.
  With the key set, all endpoints except `/health` return 401 without a
  matching `Authorization: Bearer` or `x-api-key` header. Restart the daemon
  after the key is first generated:
  `launchctl kickstart -k gui/$(id -u)/com.daari.serve`.
- Quick tunnels get a fresh random URL each start, which limits exposure but
  breaks Cursor config on every restart. For a stable, lower-profile setup use
  a **named Cloudflare tunnel** on your own domain (free; requires a Cloudflare
  account) — the URL never changes and you can add Cloudflare Access policies
  in front.
- Alternatives in the same category: ngrok (ephemeral free URLs) or Tailscale
  Funnel (stable URL tied to your tailnet identity). All of them are public
  HTTPS endpoints — the API key is what actually gates access.

Note: the tunnel requirement is Cursor's architecture, not daari's. Cursor
builds prompts on its servers and SSRF-blocks private IPs, so no BYOK setup
can call localhost directly. Claude Code, IntelliJ, VS Code, and the browser
extension all talk to `http://127.0.0.1:11435` with no tunnel.

## Alternatives for true-local E2E (no public tunnel)

- Browser extension: `packages/browser-extension/` (direct localhost usage)
- `curl` against local daemon: `http://127.0.0.1:11435/v1`
- VS Code local setup: `daari setup vscode` (same machine, no Cursor cloud hop)

## Troubleshooting

|Problem|Check|
|---|---|
|`Access to private networks is forbidden`|You are still using localhost in Cursor; switch to tunnel HTTPS URL|
|Cursor shows `Reconnecting...` + `Network Error - trouble connecting to model provider`|Verify your tunnel URL is a random `https://<name>.trycloudflare.com` hostname (not `https://api.trycloudflare.com`), then test `curl https://<name>.trycloudflare.com/health` and `daari doctor --tunnel --tunnel-url https://<name>.trycloudflare.com`|
|Empty response in Cursor (no text)|Check `~/.daari/cursor-requests.log` — look for `content_chunks: 0`. Common causes (fixed in recent builds): unrecognized `input_text` content blocks, IDE tools causing Ollama `tool_calls`, L4 model not pulled (404 then fallback). Restart `daari serve` from venv after updates.|
|Slow first reply on long prompts|Cursor context may route to L4 (`llama3.1:8b`). If not pulled, daari retries L3 after 404 — run `ollama pull llama3.1:8b` or expect ~15s L3 fallback latency.|
|Reply mentions shell/tools but didn't use them|Expected POC limitation: daari strips Cursor's 18 IDE tools for Ask, but Cursor's system prompt still describes tools; small local models may hallucinate tool narration in plain text. See [TRACKING.md](../TRACKING.md#cursor-e2e-byok--poc-2026-06-23).|
|`cloudflared: command not found`|Install: `brew install cloudflared`|
|Tunnel command exits quickly|Restart with `scripts/tunnel.sh`; it now validates `/health` before printing ready and shows copy/paste curl checks|
|Slow every request|Cache miss — verify with `daari stats`|

## Prefer latency? Cap the local tier

Cursor's Ask context is usually >250 words, which routes to L4 (`llama3.1:8b`) and pays its latency even for trivial questions. To keep chat on the fast L3 model:

```yaml
# ~/.daari/config.yaml
routing:
  max_tier_for_chat: L3
```

Or per request with the `X-Daari-Tier-Cap: L3` header (wins over config). The cap bounds both the initial tier and local confidence escalation; an explicit `X-Daari-Tier-Override` still wins over the cap.

## Verify routing (debug log)

After a Cursor chat message:

```bash
tail -10 ~/.daari/cursor-requests.log
```

Healthy Ask flow:

- `chat_completions_request` with `user_agent: Cursor/1.0`
- `tools_stripped` with `count: 18` (Ask mode)
- `stream_attempt` → optionally `stream_fallback_ok` if L4 missing
- `chat_completions_stream_done` with **`content_chunks` > 0**

Answer source: **local Ollama** (`llama3.2:3b` or `llama3.1:8b`), not Cursor built-in or frontier APIs — unless L6 escalation is configured and triggered (not used in standard Ask POC).

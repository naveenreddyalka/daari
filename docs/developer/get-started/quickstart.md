# Quickstart

**Outcome:** Send a chat completion and see an L0 cache hit on the second identical request.

## Prerequisites

- daari installed ([Install](install.md))
- Daemon running: `daari serve` (or `docker compose up`)
- For live local models: Ollama with `llama3.2:3b` (Compose pulls this for you)

## Steps

### 1. Health check

```bash
curl -fsS http://127.0.0.1:11435/health
```

### 2. First completion

```bash
curl -s http://127.0.0.1:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Daari-Meta: true" \
  -d '{"model":"daari","messages":[{"role":"user","content":"Say hi in one word"}]}'
```

Expect `daari_meta.tier` of `L3`–`L5` (or `L0`/`L1` if already cached).

### 3. Repeat — cache hit

Run the same curl again. Expect `"tier": "L0"` and `"cache_hit": true` in `daari_meta`.

### 4. Stats

```bash
daari stats
# or
curl -s http://127.0.0.1:11435/v1/daari/stats | python -m json.tool
```

### One-shot demo

```bash
./scripts/demo.sh
```

## Troubleshoot

| Symptom | Fix |
|---------|-----|
| Connection refused | Start `daari serve` or Compose |
| `/ready` fails | Ollama not up or model not pulled |
| Always L3, never L0 | Identical messages required; check `X-Daari-No-Cache` is unset |
| 401 Unauthorized | `server.api_key` set — send `Authorization: Bearer <key>` |

## Next

→ [First client](first-client.md) · [Routing tiers](../concepts/routing-tiers.md)

# Ollama backend

**Outcome:** Local L3–L5 inference via Ollama.

## Steps

```bash
ollama pull llama3.2:3b
# optional L4
ollama pull llama3.1:8b
daari serve
daari doctor
```

Optional **Flint** L4 coding recipe (Ollama ≥ 0.40.9): `daari setup models --flint`
sets `models.l4=flint` without pulling weights. As of Ollama 0.40.9, Flint runs on
Linux, Windows, and macOS. Pull later with `ollama pull flint`.

Optional **Nemotron 3.5 Bolt E4B** L3 VLM recipe (Ollama ≥ 0.40.10):
`daari setup models --nemotron-bolt` sets `models.l3=nemotron-3.5-bolt:e4b`
without pulling weights. Pull later with `ollama pull nemotron-3.5-bolt:e4b`.

Optional **LFM3** L3 local-agent recipe (Ollama ≥ 0.40.12, 256K context):
`daari setup models --lfm3` sets `models.l3=lfm3` without pulling weights.
Apple hardware first in 0.40.12; Linux/Windows support coming soon. Pull later
with `ollama pull lfm3`.

Compose stack pulls models for you (`docker compose up`).

## Config

```yaml
ollama:
  base_url: http://127.0.0.1:11434
models:
  l3: llama3.2:3b
```

Add more hosts with `routing.local_pool` (issue #170). Empty `backends` keeps the single `ollama.base_url`. A dead host is skipped; `/ready` is `degraded` when some hosts are down and `not_ready` (503) when none can serve. Chat requests return typed `backend_unavailable` (503) when the pool cannot serve the chosen tier. Set `routing.local_pool.frontier_fallback: true` (default off) to escalate those requests to L6 instead — `no_frontier`, model allowlists, budgets, and PII scrub still apply (#846).

```yaml
routing:
  local_pool:
    strategy: least_outstanding   # or round_robin
    health_interval_seconds: 15
    frontier_fallback: false      # true → L6 when all local hosts are down
    backends:
      - id: gpu-a
        base_url: http://127.0.0.1:11434
        tiers: [L3, L4, L5]
      - id: gpu-b
        base_url: http://192.168.1.10:11434
        tiers: [L3, L4]
```

## Verify

`GET /ready` succeeds; chat completions return local tiers. `daari_meta.backend_id` names the host that served.

## Decision models (`POST /v1/systemone` / `POST /v1/decisions`)

Ollama 0.35+ exposes TypeSafe/Jev-style decision models at `/v1/systemone`.
daari proxies the same shape through the gateway (and OpenAI-shaped
`POST /v1/decisions`) so clients keep API-key auth, spend metering, and
`daari_meta`. OpenAI Decisions GA parity: `input_json` (top-level or content
part), images inside per-question `instructions`, and a 400-question ceiling;
local hops fold that evidence into systemone `state`/`images`.

Built-in local catalog: `clef`, `clef-flash`, `nimble`, `tev1`, `drex-1.5`,
`microsoft-decision-1`, the Ollama 0.40.9 **d3** family (`d3`, `d3:2b`,
`d3:4b`, `d3:9b`, `d3:27b`), and the Ollama 0.40.12 Liquid AI **d1** family
(`d1`, `d1:2b`, `d1-omni`) (vendor/`:tag` variants accepted). Extend via
`decisions.local_models` without a daari release. When `systemone.enabled`
(default true), those ids also appear on OpenAI `GET /v1/models`, Anthropic-shaped
`GET /v1/models` (Accept / `anthropic-version` / `x-api-key` clients get
`capabilities.decision.supported: true`), and Ollama `/api/tags` (and `/api/show`)
with capability tag `decision` so IDE/agents can discover on-box judges without
hardcoding. Virtual-key `allowed_models` still filters `/v1/models`.

Ollama ids ending in `:cloud` (for example `clef:cloud`) are remote egress.
OpenAI and Anthropic `GET /v1/models` cards set `hosted_on` to `ollama-cloud`.
`/api/tags` and `/api/show` set `details.family` to `ollama-cloud` and add the
`remote` capability. Local ids keep `details.family` `daari` and omit both
markers.

```yaml
decisions:
  local_models: [my-judge, org/custom-decision]
```

```bash
curl -s http://127.0.0.1:11435/v1/systemone -d '{
  "model": "nimble",
  "state": "Checkout returns 500 since 9am.",
  "questions": {
    "label": {
      "type": "choice",
      "instructions": "Which label fits?",
      "criteria": {"billing": "Payments", "bug": "Errors", "other": "Else"}
    }
  }
}'
```

Ollama 0.35.1+ Clef multimodal models also accept `"images": ["<base64>", …]`
alongside `state`; daari forwards them verbatim when present.

Opt out with `systemone.enabled: false` (returns 501). Upstream is
`ollama.base_url`; when Ollama is down the route returns typed
`backend_unavailable` (503). When `systemone.base_url` is set, that root is
used instead of `ollama.base_url`. Doctor tip `decisions_local_models` fires
when systemone is on but none of the catalog models appear in Ollama
`/api/tags`, or in `GET {systemone.base_url}/v1/models` when that base is set.

## Next

→ [MLX](mlx.md) · [Docker Compose](../operations/docker-compose.md)

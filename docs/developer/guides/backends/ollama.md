# Ollama backend

**Outcome:** Local L3–L5 inference via Ollama.

daari matches Ollama ≥0.40.14 sampler-default semantics on OpenAI-compatible
ingress: when a client omits `temperature` (and other sampling knobs), daari
forwards them as absent so Ollama uses the model's packaged Modelfile defaults
instead of injecting a global `0.7`.

### Facade `/api/show` limits

The Ollama-compat facade's `POST /api/show` sets `general.architecture` to
`daari-router`. When daari knows a context window for that name
(`routing.context_windows` for L3–L5 / `daari`, a `routing.virtual_models`
target, or a published catalog limit), it reports:

- `model_info["daari-router.context_length"]` — the conventional
  `<architecture>.context_length` key Ollama ≥0.40.14 clients scan (any
  `*.context_length` suffix)
- `details.context_length` and a `num_ctx` line in `parameters`

When the catalog publishes a max output-token limit for the routed model
(for example Anthropic Haiku 5.5's 128k), show also sets
`model_info["daari-router.max_output_tokens"]`, top-level `max_output_tokens`
(same JSON field as Ollama model recommendations), and `num_predict` in
`parameters`. Unknown windows/caps are omitted — never fabricated.

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
Linux/Windows/macOS with Ollama ≥ 0.40.13 (Apple from 0.40.12). Pull later
with `ollama pull lfm3`.

Optional **LFM3-VL** L4 vision recipe (Ollama ≥ 0.40.12):
`daari setup models --lfm3-vl` sets `models.l4=lfm3-vl` without pulling weights.
Linux/Windows/macOS with Ollama ≥ 0.40.13 (Apple from 0.40.12). Pull later with
`ollama pull lfm3-vl`.

Optional **LFM3-Audio** speech-only recipe (Ollama ≥ 0.40.12):
`daari setup models --lfm3-audio` wires `tts`/`asr` to `ollama.base_url/v1` with
`model: lfm3-audio` (no weight pull). Does **not** set `models.l4` or declare
chat audio/vision capabilities — `lfm3-audio` is speech-only. Pull later with
`ollama pull lfm3-audio`.

Optional **LFM3-Omni** speech recipe (Ollama ≥ 0.40.13):
`daari setup models --lfm3-omni` wires `tts`/`asr` to `ollama.base_url/v1` with
`model: lfm3-omni` (no weight pull). Optional chat path: also set
`models.l4=lfm3-omni` for native vision+audio routing. Pull later with
`ollama pull lfm3-omni`.

### LFM3 modality matrix

| Tag | Modality | Recipe |
|-----|----------|--------|
| `lfm3` | text / long-context agent | `daari setup models --lfm3` → `models.l3` |
| `lfm3-vl` | vision | `daari setup models --lfm3-vl` → `models.l4` |
| `lfm3-audio` | speech (ASR/TTS) | `daari setup models --lfm3-audio` (speech-only; no L4) |
| `lfm3-omni` | text + vision + audio (+ speech) | `daari setup models --lfm3-omni` (speech primary; optional L4) |

Optional **gpt-oss-safeguard** decision-guardrail recipe:
`daari setup models --safeguard` writes a sample `kind: decision` input rule
targeting `gpt-oss-safeguard:20b` (no weight pull; `--dry-run` prints the plan).
VRAM: 20b ≈ 16 GB; 120b needs H100-class hardware. Edit the rule's `statement`
(question/instructions) to your written policy. Pull later with
`ollama pull gpt-oss-safeguard:20b`. See [guardrails](../features/guardrails.md).

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
`d3:4b`, `d3:9b`, `d3:27b`), the Ollama 0.40.12 Liquid AI **d1** family
(`d1`, `d1:2b`, `d1-omni`), and the Ollama 0.40.15 **AutoTrust** family
(`autotrust-jev`, `autotrust-jev:9b`, `autotrust-jev:35b`,
`autotrust-jev:27b-vl`; Apple-silicon-only in 0.40.15 — revisit on
Linux/Windows GA; 35b and 27b-vl accept images) (vendor/`:tag` variants
accepted). Extend via
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

# llama.cpp server as a local tier

**Outcome:** Pin [llama.cpp v0.8.0](https://github.com/ggml-org/llama.cpp/releases/tag/v0.8.0)
(first semver release line) as an OpenAI-compatible L3–L5 backend. Cache,
budgets, and policy stay in daari; inference stays on your GPU/CPU.

For the shared `kind: openai` pool shape (also used by vLLM / LM Studio), see
[vLLM / llama.cpp local tier](vllm-local-tier.md). This page is the
llama.cpp-specific operator guide: release pinning, `llama-server` flags,
LFM3/d1 notes, and explicit non-goals.

## Why v0.8.0

Until v0.8.0, llama.cpp published bare `b####` build tags. **v0.8.0**
(2026-10-28) starts a real release line operators can pin. Server highlights
that matter for daari:

- LiquidAI **LFM3** family (text / VL / audio / omni) and **d1-2B / d1-omni**
  decision models run everywhere llama.cpp runs.
- Chat API: deferred tools, `tool_reference` content parts, reasoning-effort
  levels from the chat template, Anthropic `/v1/messages` sampling forwarding.
- New watch-only surfaces (not wired through daari yet): `/v1/realtime`
  (OpenAI realtime protocol) and `POST /tts`.

## Pin and run `llama-server`

Build or download a **v0.8.0+** binary (or a later `0.8.x` / subsequent
semver). Example HF Hub pull + serve:

```bash
llama-server \
  -hf LiquidAI/LFM3-1.7B-GGUF \
  --port 8080 \
  --host 127.0.0.1
```

Common flags:

| Flag | Role |
|------|------|
| `-hf <org/repo>` / `-m <gguf>` | Model source |
| `--port` / `--host` | Bind (default often `8080` / all interfaces — prefer loopback) |
| `-ngl <n>` | Offload layers to GPU |
| `--reasoning off` | Disable template reasoning when the model enables thinking by default |

Health probe used by daari `kind: openai`: `GET {base_url}/v1/models`.
Completions: `POST {base_url}/v1/chat/completions`.

## daari config

```yaml
routing:
  local_pool:
    backends:
      - id: llamacpp-l3
        kind: openai
        base_url: http://127.0.0.1:8080
        model: LFM3-1.7B   # name the server advertises on /v1/models
        tiers: [L3, L4]
models:
  capabilities:
    LFM3-1.7B: [tools, json, long_context]
```

A completion served by the slot sets `daari_meta.backend_id` to the slot `id`
and `daari_meta.executor` to `openai`. `GET /ready` lists the slot.

## LFM3 / d1 on Linux vs Ollama

| Path | LFM3 / d1 availability |
|------|------------------------|
| **llama.cpp ≥ v0.8.0** | Runs on Linux / Windows / macOS wherever llama.cpp builds |
| **Ollama [0.40.12](https://github.com/ollama/ollama/releases/tag/v0.40.12)** | LFM3 + d1:2b **Apple hardware only** ("Linux/Windows coming soon" in that release note) |
| **Ollama [0.40.13](https://github.com/ollama/ollama/releases/tag/v0.40.13)** | LFM3 (incl. audio/omni) on Linux and Windows as well as Apple silicon |

Operators who need LFM3/d1 on Linux **before** Ollama's Linux port (or who
prefer a pinned `llama-server` binary) should use this guide. Prefer
`kind: ollama` when you are already on Ollama ≥0.40.13 and want its model
library UX.

## Works today through daari

- Chat completions (tools / JSON when the GGUF + template support them)
- Embeddings when the same OpenAI-compat server exposes `/v1/embeddings`
- Capability tags on `models.capabilities` (same as other `kind: openai` slots)

## Non-goals / watch items

These ship in llama.cpp v0.8.0 but are **not** daari surfaces yet:

| Upstream | Status in daari |
|----------|-----------------|
| `/v1/realtime` (conversation + transcription) | Watch only — no gateway route |
| `POST /tts` | Watch only — use [TTS backends](../backends/tts.md) / Phonon / Gradium for speech out |
| LiquidAI d1 as `/v1/systemone` decisions | **No** decisions endpoint upstream; keep using daari `systemone` / Ollama d1 wiring |
| Deferred tools / `tool_reference` parts | Upstream chat feature; daari does not require or rewrite them |

## Verify

```bash
curl -s http://127.0.0.1:8080/v1/models | head
curl -s http://127.0.0.1:11435/ready | jq '.backends // .'
```

## Next

→ [vLLM / OpenAI-compat pool](vllm-local-tier.md) · [Ollama](../backends/ollama.md) ·
[ASR](../backends/asr.md) · [Configuration overview](overview.md)

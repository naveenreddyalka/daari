# llama.cpp server as a local tier

**Outcome:** Pin [llama.cpp v1.0.0](https://github.com/ggml-org/llama.cpp/releases/tag/v1.0.0)
(first stable major, 2026-11-13) as an OpenAI-compatible L3–L5 backend. Cache,
budgets, and policy stay in daari; inference stays on your GPU/CPU.

For the shared `kind: openai` pool shape (also used by vLLM / LM Studio), see
[vLLM / llama.cpp local tier](vllm-local-tier.md). This page is the
llama.cpp-specific operator guide: release pinning, `llama-server` security
opt-ins, VRAM levers, TTS, Ripple, and explicit non-goals.

## Why v1.0.0

**v0.8.0** (2026-10-28) started the semver line. **v1.0.0** is the first stable
major operators should pin for production boxes
([blog](https://huggingface.co/blog/ggml-org/llama-cpp-v1)). Highlights that
matter for daari:

- `llama-server` security pass: SSRF / CORS / DNS-rebinding fixes; new opt-ins
  `--allow-unauthenticated-tools` and `--media-allow-private-urls`; `HF_TOKEN`
  restricted to huggingface.co.
- OpenAI-compatible **`/v1/audio/speech`** plus drama-3 TTS (fishaudio).
- **FP8 KV caches** (`-ctk` / `-ctv f8_e4m3`) and a host-memory **MoE expert
  cache** (`moe_cache_size`) — real VRAM / capacity levers.
- **Ripple-65B-Preview** text architecture — same model the
  [Ollama Ripple recipe](../../../setup/ollama.md) targets, now runnable on a
  pinned `llama-server` too.
- LiquidAI **LFM3** / **d1** continue to run wherever llama.cpp builds.

## Pin and run `llama-server`

Build or download a **v1.0.0+** binary. Prefer loopback unless you terminate TLS
and auth in front of the process:

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
| `--port` / `--host` | Bind (prefer `127.0.0.1`) |
| `-ngl <n>` | Offload layers to GPU |
| `-ctk f8_e4m3` / `-ctv f8_e4m3` | FP8 KV cache (VRAM lever) |
| `--moe-cache-size <n>` | Host-memory MoE expert cache size |
| `--reasoning off` | Disable template reasoning when the model enables thinking by default |

Health probe used by daari `kind: openai`: `GET {base_url}/v1/models`.
Completions: `POST {base_url}/v1/chat/completions`.

## Security opt-ins (leave off by default)

v1.0.0 hardened `llama-server`. Two new flags **widen** the attack surface —
daari operators should leave them **off** unless they intentionally expose the
server beyond loopback and understand the risk:

| Flag | When it matters | daari guidance |
|------|-----------------|----------------|
| `--allow-unauthenticated-tools` | Enables tools on non-loopback binds | Leave off. Put daari (keys, budgets, guardrails) in front; keep `llama-server` on loopback. |
| `--media-allow-private-urls` | Allows media fetches to private/LAN URLs | Leave off unless you control every media URL the model can request. |
| `HF_TOKEN` | Hub auth for `-hf` pulls | v1.0.0 restricts the token to huggingface.co hosts — still treat it as a secret; do not commit it. |

daari is the governance layer (virtual keys, budgets, MCP guardrails, spend
ledger). Raw `llama-server` still has no multi-tenant policy — do not expose it
on a public interface "because daari is in front" without also locking the
engine bind.

## VRAM / capacity levers

When sizing a box that co-hosts daari + `llama-server`:

- **FP8 KV cache** (`-ctk f8_e4m3`, `-ctv f8_e4m3`) cuts KV VRAM vs FP16/BF16
  caches so longer contexts or larger batches fit.
- **MoE expert cache** (`moe_cache_size` / `--moe-cache-size`) keeps hot experts
  in host memory so MoE models spend less VRAM on cold experts.

See also [Capacity and Helm](../operations/capacity-helm.md) for fleet-level
notes.

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

## TTS via llama-server

v1.0.0 adds OpenAI-compatible `POST /v1/audio/speech` (drama-3 TTS). Point
daari's existing speech proxy at the same server:

```yaml
tts:
  base_url: http://127.0.0.1:8080/v1
  model: drama-3
```

`response_format` is forwarded as the OpenAI-shaped field; use formats the
server advertises (typically `wav` / `pcm` / `mp3` depending on build). Leave
`tts.base_url` empty and `POST /v1/audio/speech` still returns **501**. Full
speech route notes: [TTS backends](../backends/tts.md).

## Ripple-65B on llama.cpp

[Ripple Preview](../../../setup/ollama.md) (#2217) is not Ollama-only on Linux.
Serve a Ripple GGUF with `llama-server` ≥ v1.0.0 and register it as an L5
`kind: openai` slot the same way as LFM3 above. Prefer Ollama's
`daari setup models --ripple` when you already run Ollama ≥ 0.40.16 and want
library UX; prefer this guide when you want a pinned `llama-server` binary.

## LFM3 / d1 on Linux vs Ollama

| Path | LFM3 / d1 availability |
|------|------------------------|
| **llama.cpp ≥ v1.0.0** | Runs on Linux / Windows / macOS wherever llama.cpp builds |
| **Ollama [0.40.12](https://github.com/ollama/ollama/releases/tag/v0.40.12)** | LFM3 + d1:2b **Apple hardware only** ("Linux/Windows coming soon" in that release note) |
| **Ollama [0.40.13](https://github.com/ollama/ollama/releases/tag/v0.40.13)** | LFM3 (incl. audio/omni) on Linux and Windows as well as Apple silicon |

Prefer `kind: ollama` when you are already on Ollama ≥0.40.13 and want its model
library UX.

## Works today through daari

- Chat completions (tools / JSON when the GGUF + template support them)
- Embeddings when the same OpenAI-compat server exposes `/v1/embeddings`
- Speech via `tts.base_url` → `llama-server` `/v1/audio/speech`
- Capability tags on `models.capabilities` (same as other `kind: openai` slots)

## Non-goals / watch items

These ship in llama.cpp v1.0.0 but are **not** first-class daari surfaces:

| Upstream | Status in daari |
|----------|-----------------|
| `/v1/realtime` (conversation + transcription) | Watch only — no gateway route |
| Built-in web UI (chat groups, markdown editor) | Engine UI only — operators use daari's HTTP API / IDE BYOK |
| Legacy `POST /tts` (non-OpenAI path) | Prefer `/v1/audio/speech` via [TTS backends](../backends/tts.md) |
| LiquidAI d1 as `/v1/systemone` decisions | **No** decisions endpoint upstream; keep using daari `systemone` / Ollama d1 wiring |
| Deferred tools / `tool_reference` parts | Upstream chat feature; daari does not require or rewrite them |
| MCP tool-call cancellation inside llama-server | Engine-side; daari MCP cancel is a separate gateway surface |

## Verify

```bash
curl -s http://127.0.0.1:8080/v1/models | head
curl -s http://127.0.0.1:11435/ready | jq '.backends // .'
```

## Next

→ [vLLM / OpenAI-compat pool](vllm-local-tier.md) · [Ollama](../backends/ollama.md) ·
[ASR](../backends/asr.md) · [TTS](../backends/tts.md) ·
[Configuration overview](overview.md)

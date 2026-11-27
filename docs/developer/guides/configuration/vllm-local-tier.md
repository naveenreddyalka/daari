# vLLM / llama.cpp server as a local tier

**Outcome:** Point daari at any OpenAI-compatible local server (vLLM, llama.cpp
server, LM Studio, SGLang, TGI) as a pool backend. Cache, budgets, and policy
stay in front; inference stays on your GPU.

## Minimum vLLM version

For `kind: openai` slots that point at **vLLM**, run **≥0.32.0**. That cut
closed a wave of security advisories (including one-request engine-crash DoS,
template injection, and socket-exhaustion class issues) —
[vLLM 0.32.0 release](https://github.com/vllm-project/vllm/releases/tag/v0.32.0).
Older servers stay reachable through the same OpenAI-compatible probe, but
operators who treat this guide as current should not stay below that floor.
The same **0.32+** floor appears for vLLM `/v1/systemone` in the
[config reference](../../reference/config.md) (`systemone.base_url`).

### 0.33.0 upgrade notes

[vLLM 0.33.0](https://github.com/vllm-project/vllm/releases/tag/v0.33.0rc3)
(GA 2026-11-02; GitHub tag `v0.33.0rc3`) is a breaking operator bump if you
pull release wheels or images on a CUDA 12.x host:

- **CUDA 13.0 only** — CUDA 12.9 wheels and `-cu129` / `-cu129-ubuntu2404`
  images are no longer published; use the default CUDA 13.0 artifacts.
- **PyTorch 2.14** — wheels/images ship with PyTorch 2.14.0.
- **`vllm/vllm` image alias** — every release image is also published under
  the shorter name (e.g. `vllm/vllm:v0.33.0`).
- **ROCm 10.0 default** — the default ROCm image/wheels move to ROCm 10.0
  (`-rocm72` still published for ROCm 7.2).

The ≥0.32.0 security floor above is unchanged; 0.33.0 is an optional upgrade
path with these artifact constraints.

### 0.34.0 upgrade notes

[vLLM 0.34.0](https://github.com/vllm-project/vllm/releases/tag/v0.34.0)
(GA 2026-11-16; first stable after 0.33) is another operator-breaking bump
for anyone running daari's L4/L5 on vLLM:

- **Model Runner V1 removed** — `VLLM_USE_V2_MODEL_RUNNER=0` now **fails at
  startup** ([#63373](https://github.com/vllm-project/vllm/pull/63373)). Drop
  that env if you still carry it.
- **Default `--block-size` is 64** (was 16)
  ([#63231](https://github.com/vllm-project/vllm/pull/63231)).
- **Extensible KV cache on by default**, and `gpu_memory_utilization`
  defaults to **1.0** — bigger cache/throughput, but TPOT can rise 6–18% at
  high concurrency. Opt out with `--gpu-memory-utilization 0.9` and/or
  `--no-enable-extensible-kv-cache`
  ([#56492](https://github.com/vllm-project/vllm/pull/56492)).
- **ROCm 7.2 images/wheels dropped** — ROCm 10.0 only
  ([#61939](https://github.com/vllm-project/vllm/pull/61939)).
- **`huggingface_hub >= 2.0.0` required**
  ([#64779](https://github.com/vllm-project/vllm/pull/64779)).

Same release also adds surfaces daari already fronts:

- **Local ASR** — Nemotron-3.5-Transcribe and Canary-1B-v2 serve
  `/v1/audio/transcriptions` (see [Speech-to-text](../backends/asr.md)).
- **Ripple-65B Preview** with `ripple` reasoning/tool parsers — a serving
  alternative to the Ollama Ripple recipe (see [Ollama setup](../../../setup/ollama.md)).
- Ops watch: `/checkpoint/prepare|status|restore` and opt-in cache-aware
  admission — capacity-relevant, not required for the OpenAI-compat pool.

The ≥0.32.0 security floor above is unchanged; 0.34.0 is the current
recommended upgrade path when you can absorb the runner / KV / ROCm moves.

## Config

`routing.local_pool.backends[].kind: openai` talks OpenAI chat-completions
(`POST {base_url}/v1/chat/completions`) and probes `GET {base_url}/v1/models`.
The slot `model` is the name that server expects (not the Ollama tag).

```yaml
routing:
  local_pool:
    backends:
      - id: vllm-gpu0
        kind: openai
        base_url: http://127.0.0.1:8000
        model: meta-llama/Llama-3.1-8B-Instruct
        tiers: [L4, L5]
models:
  capabilities:
    meta-llama/Llama-3.1-8B-Instruct: [tools, json, long_context]
```

Same shape works for llama.cpp server (`--port 8080`) and LM Studio
(`http://127.0.0.1:1234`). For llama.cpp **v1.0.0+** release pinning, security
opt-ins, TTS, Ripple, and VRAM levers, see
[llama.cpp local tier](llamacpp-local-tier.md). Capability tags on
`models.capabilities` apply to the slot model the same way they apply to
Ollama models: a tools request can use L4 when the vLLM model declares
`tools`, even if the default Ollama L4 tag does not.

Health: `kind: openai` and `kind: mlx` probe `/v1/models`. `kind: ollama`
(default) still probes `/api/version`.

## Verify

`GET /ready` lists the slot. A completion served by it sets
`daari_meta.backend_id` to the slot `id` and `daari_meta.executor` to
`openai`.

## Next

→ [Ollama backends](../backends/ollama.md) · [Speech-to-text](../backends/asr.md) · [Configuration overview](overview.md) · [Config reference (`systemone`)](../../reference/config.md)

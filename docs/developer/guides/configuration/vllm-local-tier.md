# vLLM / llama.cpp server as a local tier

**Outcome:** Point daari at any OpenAI-compatible local server (vLLM, llama.cpp
server, LM Studio, SGLang, TGI) as a pool backend. Cache, budgets, and policy
stay in front; inference stays on your GPU.

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
(`http://127.0.0.1:1234`). Capability tags on `models.capabilities` apply to
the slot model the same way they apply to Ollama models: a tools request can
use L4 when the vLLM model declares `tools`, even if the default Ollama L4
tag does not.

Health: `kind: openai` and `kind: mlx` probe `/v1/models`. `kind: ollama`
(default) still probes `/api/version`.

## Verify

`GET /ready` lists the slot. A completion served by it sets
`daari_meta.backend_id` to the slot `id` and `daari_meta.executor` to
`openai`.

## Next

→ [Ollama backends](../backends/ollama.md) · [Configuration overview](overview.md)

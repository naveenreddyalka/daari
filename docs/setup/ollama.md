# Ollama model recipes

daari ships opt-in `daari setup models` recipes that write tier tags without
pulling weights. Pull later with `ollama pull <tag>`.

## Ripple Preview (L5 agentic coding)

Ollama ≥ 0.40.16 ships [Ripple Preview](https://ollama.com/library/ripple-preview)
(65B dense, agentic coding). Apply with:

```bash
daari setup models --ripple
```

Sets `models.l5=ripple-preview` (high-memory L4 is also fine). Plan ~40 GB+
VRAM/RAM quantized. The preview tag/name may change at GA. Doctor tips when
this recipe is configured but the Ollama server is older than 0.40.16.

Ripple also runs on pinned [llama.cpp v1.0.0+](../developer/guides/configuration/llamacpp-local-tier.md)
`llama-server` as a `kind: openai` L5 slot when you prefer a binary floor over
Ollama's library UX, and on **vLLM ≥ 0.34.0** (Ripple-65B Preview with the
`ripple` reasoning/tool parsers — see
[vLLM local tier](../developer/guides/configuration/vllm-local-tier.md)).

See also the backends guide: [ollama.md](../developer/guides/backends/ollama.md).

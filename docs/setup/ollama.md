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

See also the backends guide: [ollama.md](../developer/guides/backends/ollama.md).

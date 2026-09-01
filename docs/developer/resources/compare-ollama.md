# daari vs Ollama

Ollama **runs a model**. daari **chooses a path**. daari uses Ollama as the L3–L5 backend; it does not replace it.

| | Ollama | daari |
|--|--------|-------|
| Job | Serve local GGUF/MLX-class models | Route each request to cache, tools, local, or frontier |
| Cache | None | L0 exact + L1 semantic |
| Non-AI work | Still a model call | Lt — git, lint, IDE tools |
| Clients | Ollama API / some IDE plugins | OpenAI + Anthropic + `daari setup <client>` |
| License | MIT | Apache 2.0 |

**Pick Ollama** if you only need “a model on localhost.”

**Pick daari + Ollama** if you already run Ollama and still watch Cursor send the same prompt to a frontier API.

```
ollama pull llama3.2:3b
pip install daari
daari serve
```

Second identical `curl` should show `"tier": "L0"`. Docs: [quickstart](../get-started/quickstart.md).

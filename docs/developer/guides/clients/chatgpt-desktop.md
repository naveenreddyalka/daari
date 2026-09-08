# ChatGPT Desktop

**Outcome:** ChatGPT Desktop uses daari via the Ollama-compatible facade
(Ollama v0.34+ can point local model traffic at a custom Ollama host).

## Prerequisites

- `daari serve` running
- ChatGPT Desktop with Ollama integration available (Ollama macOS app /
  v0.34+ local-model path)

## Steps

1. `daari serve` (listens on **`http://127.0.0.1:11435`** by default).
2. Keep native Ollama on **11434** if you still use it directly — daari
   proxies local tiers through Ollama; they are different ports.
3. In ChatGPT Desktop / the Ollama host setting for local models, set the
   Ollama base URL to `http://127.0.0.1:11435` (daari root — **no `/v1`**).
4. Pick model **daari** (or any L3/L4/L5 name listed by `GET /api/tags`).

Optional: send `X-Daari-Client-Id: chatgpt-desktop` when the client allows
custom headers so `daari report` attributes traffic correctly.

## What works

| Surface | Notes |
|---------|-------|
| Chat (`/api/chat`) | Streaming NDJSON and non-stream JSON through cache, tiers, budgets |
| Generate (`/api/generate`) | Same router path; prompt (+ optional `system` / `images`) |
| Embed (`/api/embed`, `/api/embeddings`) | Mapped to daari's embedding model (L1 / `nomic-embed-text`) |
| Tags / show / version / ps | Virtual model cards so the client can discover `daari` |

Ollama 0.34 OpenAI-compat extras (tool search, response compaction, and
other unknown fields) are ignored gracefully — they must not 4xx/5xx.

## Limitations

- The facade does not run Ollama's native model pull/create APIs; install
  models with `ollama pull` as usual, then route through daari.
- Streaming responses use Ollama NDJSON token fields (`prompt_eval_count` /
  `eval_count`); `daari_meta` is attached on non-stream JSON only.
- ChatGPT Desktop UI labels may still say "Ollama" — that is expected; the
  host URL is what sends traffic through daari.

## Troubleshoot

| Problem | Fix |
|---------|-----|
| Empty model list | Daemon down, or URL still points at 11434 / includes `/v1` |
| No cache / budget effect | Confirm the host is **11435** (daari), not bare Ollama |
| Embed 400 unknown model | Use `daari` or the configured `cache.l1.embedding_model` |

## Next

→ [JetBrains (same facade)](intellij.md) · [Clients and gateways](../../concepts/clients-and-gateways.md)

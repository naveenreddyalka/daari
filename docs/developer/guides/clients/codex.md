# Codex CLI

**Outcome:** The Codex CLI uses daari for cache, budgets, and local tiers
before frontier calls.

**Fast path:** `daari configure codex` (prints the OpenAI-compatible base URL,
the `ollama launch codex` host, and a verify curl; see also `daari setup codex`).
Does not edit Codex config files.

## Prerequisites

- `daari serve` running (default `http://127.0.0.1:11435`)
- Codex CLI installed

## Steps

1. `daari serve`.
2. Point Codex at the OpenAI-compatible base URL
   `http://127.0.0.1:11435/v1` (API key `daari-local` unless
   `server.api_key` is set). Pick model **daari**.
3. If you start Codex with `ollama launch codex`, set the Ollama host to
   daari's root `http://127.0.0.1:11435` (**no `/v1`**). Leave native Ollama
   on **11434** when you still use it directly.

Optional: send `X-Daari-Client-Id: codex` when the client allows custom
headers so `daari report` attributes traffic correctly.

Verify:

```bash
curl -sS -H "Authorization: Bearer daari-local" http://127.0.0.1:11435/v1/models
```

## Limitations

- Codex config files are not written. Preferences for the CLI are
  operator-managed; this recipe only prints the steps.
- `ollama launch codex` talks to the Ollama facade (root URL). The
  OpenAI-compatible path is `/v1`.

## Next

→ [ChatGPT Desktop (same Ollama host)](chatgpt-desktop.md) · [OpenAI SDK](openai-sdk.md)

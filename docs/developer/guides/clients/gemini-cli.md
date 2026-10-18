# Gemini CLI

**Outcome:** Operators learn that daari does not serve the native Gemini API,
and which clients do talk to the daemon.

**Fast path:** `daari configure gemini-cli` (also `daari setup gemini-cli`).
Prints a notice and does not write `settings.json` or any other config file.

## What daari serves

The daemon is OpenAI-shaped, Anthropic-shaped, and Ollama-shaped. The native
Gemini API is not a daari surface. Point Codex or OpenCode at the gateway
instead:

```bash
daari configure codex
daari configure opencode
```

Those clients use the OpenAI-compatible path (cache, local tiers, then
frontier).

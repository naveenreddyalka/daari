# Manual Cursor setup — Phase A

> Use this until `daari setup cursor` ships in Phase A.1.

## Prerequisites

- daari daemon running: `daari serve` (default `http://127.0.0.1:11435/v1`)
- Ollama running with default model (e.g. `llama3.2:3b`)

## Steps

1. Open **Cursor Settings** → **Models**
2. Add a **custom OpenAI-compatible** model:
   - **Base URL:** `http://127.0.0.1:11435/v1`
   - **API key:** `daari-local` (any string unless you set `DAARI_API_KEY`)
   - **Model name:** `daari` (or match your `config.yaml`)
3. Select the custom model for chat/agent
4. Verify: send a prompt twice — second should hit L0 cache (`daari stats`)

## Troubleshooting

| Problem | Check |
|---------|-------|
| Connection refused | `daari serve` running? Port 11435? |
| Slow every request | Cache miss — check `daari stats` for L0 hits |
| Agent mode errors | Expected in MVP — see [ADR-0004](../adr/0004-agent-tool-call-compatibility.md) |

## Revert

Remove custom model from Cursor settings. No daari files are modified in manual setup.

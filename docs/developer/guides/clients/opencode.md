# OpenCode

**Outcome:** OpenCode uses daari for cache, budgets, and local tiers before
frontier calls, over the OpenAI-compatible `/v1` surface.

**Fast path:** `daari configure opencode` (prints a v2 provider snippet and a
verify curl; see also `daari setup opencode`). Does not edit OpenCode config
files.

## Prerequisites

- `daari serve` running (default `http://127.0.0.1:11435`)
- OpenCode installed

## Steps

1. `daari serve`.
2. Add a provider whose `settings.baseURL` is
   `http://127.0.0.1:11435/v1`. Use package
   `@opencode/ai/providers/openai-compatible`. Put the key in the environment
   and reference `{env:DAARI_API_KEY}` so the snippet is safe to commit.
   Pick model **daari**.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "providers": {
    "daari": {
      "package": "@opencode/ai/providers/openai-compatible",
      "settings": {
        "baseURL": "http://127.0.0.1:11435/v1",
        "apiKey": "{env:DAARI_API_KEY}"
      }
    }
  }
}
```

Older OpenCode configs use `provider.daari.options.baseURL` (same URL, still
ending in `/v1`) instead of `providers.daari.settings.baseURL`.

Optional: send `X-Daari-Client-Id: opencode` when the client allows custom
headers so `daari report` attributes traffic correctly.

Verify:

```bash
curl -sS -H "Authorization: Bearer daari-local" http://127.0.0.1:11435/v1/models
```

## Limitations

- OpenCode config files are not written. Project vs user config is
  operator-managed; this recipe only prints the steps.
- daari speaks OpenAI-compatible `/v1`, not a separate OpenCode protocol.

## Next

→ [Codex CLI](codex.md) · [OpenAI SDK](openai-sdk.md)

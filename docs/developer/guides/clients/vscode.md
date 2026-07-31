# VS Code

**Outcome:** VS Code OpenAI-compatible settings point at daari.

## Steps

```bash
daari setup vscode --dry-run
daari setup vscode
```

Writes `openai.baseUrl` → `http://127.0.0.1:11435/v1` and a local API key marker into user `settings.json` (backup first).

## Verify

Use an extension that honors those settings; confirm with `daari stats`.

## Undo

```bash
daari setup --undo vscode
```

## Next

→ [OpenAI SDK](openai-sdk.md)

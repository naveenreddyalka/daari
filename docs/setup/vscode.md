# VS Code setup (minimal)

Prefer automated setup:

```bash
daari setup vscode --dry-run
daari setup vscode
```

## What this does

- Detects VS Code user settings path.
- Writes OpenAI-compatible keys in `settings.json`:
  - `openai.baseUrl`: `http://127.0.0.1:11435/v1`
  - `openai.apiKey`: `daari-local`
- Adds `daari.setup.vscode` marker block for idempotency.
- Creates backups before changing existing settings files.

## Undo

```bash
daari setup --undo vscode
```

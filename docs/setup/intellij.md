# IntelliJ setup (minimal)

Prefer automated setup:

```bash
daari setup intellij --dry-run
daari setup intellij
```

## What this does

- Detects JetBrains IntelliJ config directories.
- Writes `options/daari-openai-compat.json` with OpenAI-compatible defaults:
  - base URL: `http://127.0.0.1:11435/v1`
  - API key: `daari-local`
  - model: `daari`
- Creates backups for any existing files before overwrite.

## What you still do in IDE

JetBrains AI Assistant/OpenAI-compatible model selection still happens in IntelliJ UI.
Use the helper JSON values above when selecting custom provider settings.

## Undo

```bash
daari setup --undo intellij
```

# Claude Code setup (minimal)

Prefer automated setup:

```bash
daari setup claude-code --dry-run
daari setup claude-code
```

## What this does

- Writes `~/.claude/daari-openai-compat.env` with:
  - `OPENAI_BASE_URL=http://127.0.0.1:11435/v1`
  - `OPENAI_API_KEY=daari-local`
  - `OPENAI_MODEL=daari`
- Writes `~/.claude/daari-config-pointer.txt` with a pointer to the env file.
- Creates backups when overwriting existing files.

## Use it

```bash
source ~/.claude/daari-openai-compat.env
claude
```

## Undo

```bash
daari setup --undo claude-code
```

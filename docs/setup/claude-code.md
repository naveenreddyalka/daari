# Claude Code setup (one-click)

```bash
daari setup claude-code --dry-run   # preview
daari setup claude-code             # apply
```

## What this does

Merges an `env` block into `~/.claude/settings.json` (a backup is taken first):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:11435",
    "ANTHROPIC_AUTH_TOKEN": "daari-local",
    "ANTHROPIC_MODEL": "daari"
  }
}
```

Claude Code reads this on launch — no manual `source` or shell exports needed.
Existing settings (theme, other env vars) are preserved.

## Use it

```bash
daari serve   # if the daemon is not already running
claude        # chats now route through daari's local tiers
```

daari serves Claude Code via its Anthropic-compatible `/v1/messages` endpoint,
including the top-level `system` prompt and full tool passthrough (issue #84):
agent turns carry `tools` and `tool_use`/`tool_result` blocks through the
router to the local model, so file edits and command runs work end-to-end.

## Limits

- Plain chat routes through the local tiers (L0 cache → L3/L4/L5 → optional L6).
- Agent/tool turns are executed by the local model (L3/L4). Small local models
  are noticeably weaker at multi-step agentic work than Claude — expect
  reduced quality on complex coding tasks, not missing functionality.
- Force plain-chat handling per request with the `X-Daari-Tools: strip` header.

## Undo (one-click uninstall)

```bash
daari setup --undo claude-code
```

Restores the pre-setup `settings.json` from the latest backup. If no backup
exists (fresh install), the daari-managed `ANTHROPIC_*` keys are stripped
instead, leaving any settings you added untouched.

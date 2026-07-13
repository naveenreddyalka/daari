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
including the top-level `system` prompt Claude Code sends.

## Limits

- Plain chat routes through the local tiers (L0 cache → L3/L4/L5 → optional L6).
- Claude Code's tool/agent turns need Anthropic tool passthrough, which daari
  does not implement yet — heavy agentic sessions will degrade. Track progress
  in issue #81.

## Undo

```bash
daari setup --undo claude-code
```

Restores the pre-setup `settings.json` from the latest backup.

# Claude Code

**Outcome:** Claude Code chats and tools route through daari's Anthropic gateway.

**Fast path:** `daari configure claude-code` (writes settings + prints a verify curl; see also `daari setup claude-code`).

## Prerequisites

- `daari serve` on `http://127.0.0.1:11435`
- Claude Code installed

## Steps

```bash
daari setup claude-code --dry-run
daari setup claude-code
daari serve   # if not already running
claude
```

Merges into `~/.claude/settings.json` (backup first):

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:11435",
    "ANTHROPIC_AUTH_TOKEN": "daari-local",
    "ANTHROPIC_MODEL": "daari"
  }
}
```

No tunnel required (localhost is fine).

## Verify

Chat once, then `daari report`. Agent turns use `/v1/messages` with tool passthrough.

## Thinking budgets

Claude Code's request-level `thinking: {type, budget_tokens}` is forwarded
verbatim on L6 Anthropic escalations. Locally it maps onto Ollama `think` via
`reasoning_effort`:

| `budget_tokens` | local `think` |
|-----------------|---------------|
| ≤ 2048 | `low` |
| ≤ 8192 | `medium` |
| > 8192 | `high` |
| `type: disabled` | omitted |

## Troubleshoot

| Problem | Fix |
|---------|-----|
| Still hits Anthropic cloud | Confirm settings.json env block; restart `claude` |
| Tools fail on small models | Expected limitation of L3 size — try L4 or frontier for hard agent tasks |

## Undo

```bash
daari setup --undo claude-code
```

## Next

→ [Project profiles](../configuration/project-profiles.md)

# JetBrains (IntelliJ)

**Outcome:** AI Assistant uses daari via the Ollama-compatible facade.

## Prerequisites

- `daari serve` running
- JetBrains AI Assistant available

## Steps

1. `daari serve`
2. **Settings → Tools → AI Assistant → Models** (or Third-party AI providers)
3. Enable **Ollama**, URL `http://127.0.0.1:11435`
4. Pick model **daari**

`/api/tags` and `/api/show` advertise Ollama-shaped `capabilities` derived from
the mapped tier (`completion`, plus `tools` / `vision` / `thinking` when the
catalog or model name supports them), so capability-aware clients keep tool
calling and thinking UI enabled against the facade. When `thinking` is in
capabilities, `/api/show` also returns a `thinking` controls object (`values`:
`low` / `medium` / `high`, `default`: `medium`) so clients can discover allowed
think levels. Ollama **0.40.7+** clients also read `renderer`, `parser`, and
`template_source` on `/api/show`; the facade returns stable stubs (`""` /
`""` / `"model"`) so feature detection matches a templateless native model.
`/api/tags` is unchanged (those keys are show-only).

Helper (prints steps + reference JSON):

```bash
daari setup intellij --dry-run
daari setup intellij
```

## Verify

Send a chat from the IDE; `daari report` shows traffic (set `X-Daari-Client-Id: intellij` if your plugin supports headers).

## Troubleshoot

| Problem | Fix |
|---------|-----|
| Empty model list | Daemon down or wrong URL (no `/v1` suffix for Ollama facade) |
| Provider not writable from CLI | Expected — toggle Ollama once in the IDE UI |

## Next

→ [Clients and gateways](../../concepts/clients-and-gateways.md)

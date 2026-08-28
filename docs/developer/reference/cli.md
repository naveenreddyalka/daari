# CLI reference

Entry point: `daari` (Typer).

## Top-level

| Command | Purpose |
|---------|---------|
| `serve` | Run the gateway daemon |
| `stats` | Tier counters |
| `doctor` | Health / suggest-models |
| `install` | Convenience installer helpers |
| `onboard` | pip/brew first-run (Ollama + default models) |
| `feedback` | Record accept/reject |
| `trace` | Show a request trace |
| `report` | Savings / usage ledger |
| `profile` | Local hardware profile |

## `setup`

| Command | Purpose |
|---------|---------|
| `setup` / `setup all` | Wizard |
| `setup cursor` | Cursor BYOK (+ `--tunnel`) |
| `setup claude-code` | Anthropic env merge |
| `setup intellij` | JetBrains helper |
| `setup vscode` | VS Code settings |
| `setup openai-compat` | SDK env template |
| `setup models` | Pull recommended models |
| `setup frontier-key` | Frontier env hints |
| `setup --undo <client>` | Revert |

## Other groups

| Group | Commands |
|-------|----------|
| `context` | `clear` |
| `cache` | `prune` |
| `learn` | `stats`, `export-stats`, `aggregates`, `propose-defaults`, `outcome`, `examples`, `export-dataset`, `train-router`, `finetune`, `mlx-lm`, `deploy`, `recommend` |
| `org-cache` | `serve` |
| `org-learning` | `stats`, `sync`, `export` |
| `web-ui` | `serve` |
| `project` | `init`, `show` |
| `keys` | `create`, `list`, `revoke` |
| `enterprise` | `bootstrap`, `policy-sync` |
| `service` | `install`, `status`, `uninstall` (user systemd / launchd) |

Use `daari <cmd> --help` for flags.

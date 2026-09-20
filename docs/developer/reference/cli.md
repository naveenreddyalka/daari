# CLI reference

Entry point: `daari` (Typer).

## Top-level

| Command | Purpose |
|---------|---------|
| `serve` | Run the gateway daemon |
| `stats` | Tier counters (`GET /v1/daari/stats` JSON) |
| `doctor` | Health / suggest-models |
| `install` | Convenience installer helpers |
| `onboard` | pip/brew first-run (Ollama + default models) |
| `feedback` | Record accept/reject |
| `trace` | Show a request trace |
| `report` | Savings / usage ledger |
| `usage` | Alias of `report` |
| `spend` | Per-request chargeback export (`export`, `--tier`) — see [chargeback](../guides/observability/chargeback.md) |
| `profile` | Local hardware profile |
| `route` | Routing helpers (`preview`) |
| `audit` | Enterprise audit log (`list` / `export` / `verify`) |
| `configure` | Interactive config helpers |
| `config` | Validate `config.yaml` (`validate`) |
| `prune` | Retention prune (traces / usage / feedback) |

## `setup`

| Command | Purpose |
|---------|---------|
| `setup` / `setup all` | Wizard |
| `setup cursor` | Cursor BYOK (+ `--tunnel`) |
| `setup claude-code` | Anthropic env merge |
| `setup claude-desktop` | Claude Desktop helper |
| `setup intellij` | JetBrains helper |
| `setup vscode` | VS Code settings |
| `setup openai-compat` | SDK env template |
| `setup models` | Pull recommended models |
| `setup frontier-key` | Frontier env hints |
| `setup --undo <client>` | Revert |

## `route`

| Command | Purpose |
|---------|---------|
| `route preview` | Show which tier a prompt would take (`--model`, `--latency-budget-ms`) |

## Other groups

| Group | Commands |
|-------|----------|
| `context` | `clear` |
| `cache` | `prune`, `invalidate` (`--model`, `--hash`, `--team`, `--key`, `--token` for SSO/master Bearer when calling a running daemon) |
| `learn` | `stats`, `export-stats`, `propose-defaults`, `examples`, `export-dataset`, `train-router`, `finetune`, `deploy`, `recommend` |
| `org-cache` | `serve` |
| `org-learning` | `stats`, `sync`, `export` |
| `web-ui` | `serve` |
| `project` | `init`, `show` |
| `keys` | `create`, `update`, `list`, `revoke`, `rotate`, `team-create`, `team-update`, `export`, `import` |
| `enterprise` | `bootstrap`, `policy-sync` |
| `service` | `install`, `status`, `restart`, `uninstall` (user systemd / launchd) |
| `audit` | `list`, `export`, `verify` |

Use `daari <cmd> --help` for flags.

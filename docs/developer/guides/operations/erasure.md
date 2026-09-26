# Subject erasure (`daari erase`)

Operator guide for GDPR/CCPA-style subject deletion across daari's local stores
([#1130](https://github.com/naveenreddyalka/daari/issues/1130)).

## Command

```bash
# Preview matches (no writes)
daari erase --key KEY_ID --dry-run
daari erase --team TEAM_ID --dry-run
daari erase --user USER_ID --dry-run

# Apply (requires --yes)
daari erase --key KEY_ID --yes
```

Exactly one of `--key`, `--team`, or `--user` is required.

## What is covered

| Store | Match |
|-------|--------|
| Spend ledger | `key_id` / `team_id` / `client_id` (for `--user`) |
| Usage ledger | `client_usage` + `user_usage` (aggregate `usage` has no tenant column) |
| Request log | JSONL lines whose payload mentions the subject |
| Responses | `owner_key_id` (key; team expands to member keys) |
| Files | `owner_key_id` (same) |
| Batches | `governance.key_id` / `team_id` / `user` |
| Idempotency | principal `vk:{key_id}` |
| Cache (L0/L1) | scoped entries via existing `invalidate(key_id=…\|team_id=…)` |

Dry-run prints per-store **match** counts. Apply prints per-store **deleted** counts.

## Audit trade-off

The append-only audit hash chain is **not** rewritten. Erasure records a new
`compliance.erase` event with subject kind/id and per-store counts. Prior audit
rows that mention the subject remain until the normal `observability.retention`
audit window expires (`daari prune`). That preserves chain integrity while still
leaving an operator-visible trail of the erasure itself.

## Backends

SQLite is the default path. Postgres-backed spend/usage/responses/files/idempotency
stores expose the same erase helpers (covered by unit tests with the existing
`memory:` doubles where applicable).

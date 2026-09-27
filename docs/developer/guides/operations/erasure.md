# Subject erasure (`daari erase`)

Operator guide for GDPR/CCPA-style subject deletion across daari's local stores
([#1130](https://github.com/naveenreddyalka/daari/issues/1130),
[#1170](https://github.com/naveenreddyalka/daari/issues/1170)).

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
| Spend ledger | `key_id` / `team_id`; for `--user`, **`user_id` OR `client_id`** (legacy client mapping kept) |
| Usage ledger | `client_usage` + `user_usage` (aggregate `usage` has no tenant column) |
| Request log | JSONL lines whose payload mentions the subject |
| Responses | `owner_key_id` (key; team expands to member keys) |
| Files | `owner_key_id` (same) |
| Batches | `governance.key_id` / `team_id` / `user` (sqlite **or** `batches.backend=postgres`) |
| Idempotency | principal `vk:{key_id}` |
| Cache (L0/L1) | scoped entries via `invalidate(key_id=…\|team_id=…)`; honors `cache.backend=redis` |
| Traces | steps JSON containing the subject id (sqlite or postgres observability backend) |

Dry-run prints per-store **match** counts. Apply prints per-store **deleted** counts.
If a cache backend cannot be scanned (for example Redis unreachable), dry-run
prints `cache: unknown` instead of a misleading `0`.

## Audit trade-off

The append-only audit hash chain is **not** rewritten. Erasure records a new
`compliance.erase` event with subject kind/id and per-store counts. Prior audit
rows that mention the subject remain until the normal `observability.retention`
audit window expires (`daari prune`). That preserves chain integrity while still
leaving an operator-visible trail of the erasure itself.

## Backends

SQLite is the default path. Fleet backends are included in the same sweep:

- Postgres spend / usage / responses / files / idempotency / batches / traces
- Redis L0 / L1 when `cache.backend=redis`

Failures to reach a fleet store are logged (`erasure.cache_failed` and similar);
they are never silently reported as zero matches on dry-run.

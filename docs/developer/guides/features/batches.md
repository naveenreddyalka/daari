# OpenAI Batch API

daari exposes OpenAI-compatible `POST/GET /v1/batches` (and cancel) so overnight
eval/drain jobs can run on idle local tiers. Pair with `/v1/files` for the stock
SDK flow (`files.create` → `batches.create(input_file_id=…)` → download
`output_file_id`).

## Durability

Jobs, items, and results persist to SQLite at `batches.path` (default
`~/.daari/batches/jobs.sqlite3`) when `batches.backend: sqlite` (default). A
gateway restart reloads unfinished `validating` / `in_progress` jobs and
continues draining pending items; an item that was mid-flight at crash is
retried once. Jobs past `expires_at` with pending work become `expired`
(remaining items skipped) on read or resume.

## Multi-replica (Postgres)

For a multi-replica fleet, point batches and files at the same Postgres the
ledger already uses:

```yaml
observability:
  backend: postgres
  postgres_url: postgresql://daari:daari@postgres:5432/daari
batches:
  backend: postgres
  claim_ttl_seconds: 90   # reclaim a crashed drainer's job after this
files:
  backend: postgres
responses:
  backend: postgres
```

Jobs, file content, and stored Responses (`store: true`, `previous_response_id`,
`background`) are then shared across replicas. Only one replica drains
a given batch at a time (claim + heartbeat); a crashed worker's claim expires
after `claim_ttl_seconds` and another replica resumes. Keep batches/files/
responses on postgres when using those APIs across pods. Single-node
SQLite remains the zero-dependency default.

Helm chart defaults stay at one replica until `postgres.enabled: true`. With that
flag the Deployment sets `DAARI_BATCHES__BACKEND` / `DAARI_FILES__BACKEND` /
`DAARI_RESPONSES__BACKEND` / `DAARI_OBSERVABILITY__BACKEND` to `postgres` for you.
NOTES and `daari doctor` warn if effective replicas (or HPA min) are greater than 1
while those backends are still SQLite — see
[Capacity and Helm](../operations/capacity-helm.md).

## Idle yield

With `batches.yield_to_interactive: true` (default), the worker checks interactive
HTTP in-flight count before each item and waits when any interactive request is
active (`batch.waiting_for_idle`). Set `yield_to_interactive: false` to restore
immediate drain. Poll interval: `batches.idle_poll_seconds` (default `0.25`).

## Config

```yaml
batches:
  enabled: true
  path: ~/.daari/batches/jobs.sqlite3
  yield_to_interactive: true
  idle_poll_seconds: 0.25
files:
  enabled: true
  path: ~/.daari/files
  max_bytes: 104857600
  retention_days: 0          # 0 = forever; set >0 to prune expired uploads
responses:
  backend: sqlite            # or postgres with observability.postgres_url
  retention_days: 0          # 0 = forever; prune via daari prune / daily sweep
```

Stored Responses (`store: true`) keep `created_at` at first write. When
`responses.retention_days` is greater than zero, `daari prune` and the daily
retention sweep delete older rows on both SQLite and Postgres backends.

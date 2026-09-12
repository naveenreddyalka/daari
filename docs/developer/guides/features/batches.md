# OpenAI Batch API

daari exposes OpenAI-compatible `POST/GET /v1/batches` (and cancel) so overnight
eval/drain jobs can run on idle local tiers. Pair with `/v1/files` for the stock
SDK flow (`files.create` → `batches.create(input_file_id=…)` → download
`output_file_id`).

## Durability

Jobs, items, and results persist to SQLite at `batches.path` (default
`~/.daari/batches/jobs.sqlite3`). A gateway restart reloads unfinished
`validating` / `in_progress` jobs and continues draining pending items; an item
that was mid-flight at crash is retried once. Jobs past `expires_at` with
pending work become `expired` (remaining items skipped) on read or resume.

## Multi-replica caveat

Persistence is **per process / per data directory**. The Helm chart's default
`replicaCount: 2` does **not** share batch state across pods — a
`GET /v1/batches/{id}` may hit a replica that never created the job. For
durable multi-replica drain, pin a single replica (or shared volume) until
cross-replica routing lands. Single-node and Docker Compose one-replica
deploys are the supported path today.

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
```

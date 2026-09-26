# Backup and restore

Full-state snapshot of durable daari stores
([#1131](https://github.com/naveenreddyalka/daari/issues/1131)).

## Create

```bash
mkdir -p ~/.daari/backups
daari backup create ~/.daari/backups/daari-$(date -u +%Y%m%d).tar.gz
```

The archive contains:

- `manifest.json` — daari version, archive schema version, per-store backends
- `stores/*` — every sqlite / JSONL / files directory daari owns on this host

Stores configured with a **postgres** backend are listed in the manifest as
`external` with the exact `pg_dump` command to run (not embedded in the
tarball).

## Restore

```bash
# Empty data dir (or pass --force to overwrite same-version files)
daari backup restore ~/.daari/backups/daari-YYYYMMDD.tar.gz
daari backup restore ~/.daari/backups/daari-YYYYMMDD.tar.gz --force
```

Archives whose `archive_schema_version` is **newer** than the running binary
are refused — upgrade daari first.

Postgres tables are not restored by this command; use `pg_restore` with the
dump you took alongside the archive.

## Cold vs live (SQLite WAL)

- Prefer a **cold** backup: stop the daemon, then `daari backup create`.
- A live backup of SQLite files can miss uncheckpointed WAL pages. If you must
  back up while running, run `sqlite3 <db> 'PRAGMA wal_checkpoint(FULL);'` per
  file first, or accept a best-effort snapshot.

## Postgres runbook

1. Note `pg_dump` lines printed by `daari backup create` (also in the
   manifest).
2. Run each dump into `~/.daari/backups/pg-*.sql`.
3. On restore: restore the tarball (sqlite/jsonl), then `pg_restore` / `psql`
   the SQL dumps into the target DSN.

## Restore drill checklist

1. Spin up an empty data dir / fresh Postgres schema.
2. `daari backup restore <archive.tar.gz>`
3. Restore any postgres dumps.
4. `daari doctor` and `daari keys list` / `daari audit list --limit 5`.
5. Confirm spend / usage counts match the pre-backup baseline.

## Doctor

`daari doctor` emits an optional hint when no `*.tar.gz` newer than 7 days is
found under `~/.daari/backups/`.

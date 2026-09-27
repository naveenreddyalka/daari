# Backup and restore

Full-state snapshot of durable daari stores
([#1131](https://github.com/naveenreddyalka/daari/issues/1131),
[#1171](https://github.com/naveenreddyalka/daari/issues/1171)).

## Create

```bash
mkdir -p ~/.daari/backups
daari backup create ~/.daari/backups/daari-$(date -u +%Y%m%d).tar.gz
```

### Optional encryption (#1176)

Default archives are plaintext `.tar.gz` (backward compatible). Opt in with
`--encrypt openssl` or `--encrypt age` (subprocess to the host binary; no new
Python crypto dependency):

```bash
# openssl AES-256-CBC (passphrase in env; plaintext .tar.gz is removed after encrypt)
export DAARI_BACKUP_PASS='use-a-long-secret'
daari backup create ~/.daari/backups/daari.tar.gz --encrypt openssl
# writes ~/.daari/backups/daari.tar.gz.enc

# age recipient (identity file used on restore)
export DAARI_BACKUP_AGE_RECIPIENT='age1…'
daari backup create ~/.daari/backups/daari.tar.gz --encrypt age --age-recipient "$DAARI_BACKUP_AGE_RECIPIENT"
# writes ~/.daari/backups/daari.tar.gz.age
```

Use `--passphrase-env OTHER_VAR` if the passphrase lives under a different name.

The archive contains:

- `manifest.json` — daari version, archive schema version, per-store backends
- `stores/*` — every sqlite / JSONL / files directory daari owns on this host
- Rotated request-log siblings (`cursor-requests.log.1`, `.2`, …) when present

Stores configured with a **postgres** backend — including batches
(`daari_batch_jobs`) and files (`daari_files`) — are listed in the manifest as
`external` with the exact `pg_dump` command to run (not embedded in the
tarball).

## Restore

```bash
# Stop daari first (restore probes GET /health and refuses if the daemon answers)
daari backup restore ~/.daari/backups/daari-YYYYMMDD.tar.gz
daari backup restore ~/.daari/backups/daari-YYYYMMDD.tar.gz --force
```

Encrypted archives decrypt in a temp directory before restore:

```bash
export DAARI_BACKUP_PASS='use-a-long-secret'
daari backup restore ~/.daari/backups/daari.tar.gz.enc --force

export DAARI_BACKUP_AGE_IDENTITY=~/.age/daari-backup.txt
daari backup restore ~/.daari/backups/daari.tar.gz.age --force --age-identity "$DAARI_BACKUP_AGE_IDENTITY"
```

If the archive is encrypted and no passphrase/identity is supplied, restore
exits with a clear error (it never silently skips decryption).

If you are certain no process holds the target stores but `/health` still
answers (stale proxy, wrong port), pass both overwrite and the interlock override:

```bash
daari backup restore ARCHIVE.tar.gz --force --i-know-server-is-stopped
```

Archives whose `archive_schema_version` is **newer** than the running binary
are refused — upgrade daari first.

Postgres tables are not restored by this command; use `pg_restore` with the
dump you took alongside the archive.

## Cold vs live (SQLite WAL)

- Prefer a **cold** backup: stop the daemon, then `daari backup create`.
- Restore always prefers a stopped daemon: a successful `/health` probe blocks
  overwrite unless `--i-know-server-is-stopped` is set.
- A live backup of SQLite files can miss uncheckpointed WAL pages. If you must
  back up while running, run `sqlite3 <db> 'PRAGMA wal_checkpoint(FULL);'` per
  file first, or accept a best-effort snapshot.

## Postgres runbook

1. Note `pg_dump` lines printed by `daari backup create` (also in the
   manifest). Batches and files appear here when their backends are postgres.
2. Run each dump into `~/.daari/backups/pg-*.sql`.
3. On restore: restore the tarball (sqlite/jsonl), then `pg_restore` / `psql`
   the SQL dumps into the target DSN.

## Restore drill checklist

1. Spin up an empty data dir / fresh Postgres schema.
2. Stop daari (or confirm `/health` fails).
3. `daari backup restore <archive.tar.gz>`
4. Restore any postgres dumps.
5. `daari doctor` and `daari keys list` / `daari audit list --limit 5`.
6. Confirm spend / usage counts match the pre-backup baseline.

## Doctor

`daari doctor` emits an optional hint when no `*.tar.gz` (or encrypted
`.tar.gz.enc` / `.tar.gz.age`) newer than 7 days is found under
`~/.daari/backups/`. When recent backups exist but are all plaintext, doctor
suggests `--encrypt openssl`.

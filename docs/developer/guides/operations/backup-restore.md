# Backup and restore

Full-state snapshot of durable daari stores
([#1131](https://github.com/naveenreddyalka/daari/issues/1131),
[#1171](https://github.com/naveenreddyalka/daari/issues/1171),
[#1177](https://github.com/naveenreddyalka/daari/issues/1177)).

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
- `stores/pg/*.sql` — embedded Postgres dumps when `pg_dump` is on PATH (#1177)

Stores configured with a **postgres** backend — including batches
(`daari_batch_jobs`) and files (`daari_files`) — are embedded into
`stores/pg/<name>.sql` when `pg_dump` is available. The manifest marks those
rows `backend=embedded` with `size_bytes` and `sha256`. If `pg_dump` is missing
or a dump fails, the row stays `external` with the exact `pg_dump` hint (create
still exits 0). Pass `--require-pg-dump` to fail instead:

```bash
daari backup create ~/.daari/backups/daari.tar.gz --require-pg-dump
```

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

Embedded Postgres dumps are listed on restore with their `stores/pg/*.sql`
paths. To load them into the configured DSN (`observability.postgres_url`)
when `psql` is on PATH:

```bash
daari backup restore ARCHIVE.tar.gz --force --restore-pg
```

Without `--restore-pg`, extract the archive (or `tar -tzf ARCHIVE | grep stores/pg`)
and run `psql --dbname="$DSN" -f stores/pg/<name>.sql` yourself. External
(hint-only) stores still need a manual `pg_dump` taken at backup time.

## Cold vs live (SQLite WAL)

- Prefer a **cold** backup: stop the daemon, then `daari backup create`.
- Restore always prefers a stopped daemon: a successful `/health` probe blocks
  overwrite unless `--i-know-server-is-stopped` is set.
- A live backup of SQLite files can miss uncheckpointed WAL pages. If you must
  back up while running, run `sqlite3 <db> 'PRAGMA wal_checkpoint(FULL);'` per
  file first, or accept a best-effort snapshot.

## Postgres runbook

1. Prefer `pg_dump` on PATH so `daari backup create` embeds dumps under
   `stores/pg/` (use `--require-pg-dump` in CI/cron if you need a hard fail).
2. If create printed `external` lines, run those `pg_dump` commands into
   `~/.daari/backups/pg-*.sql` beside the tarball.
3. On restore: restore the tarball (sqlite/jsonl), then either
   `daari backup restore … --restore-pg` for embedded dumps, or
   `psql` / `pg_restore` any external SQL dumps into the target DSN.

## Restore drill checklist

1. Spin up an empty data dir / fresh Postgres schema.
2. Stop daari (or confirm `/health` fails).
3. `daari backup restore <archive.tar.gz> --restore-pg` (when dumps are embedded).
4. Restore any remaining external postgres dumps.
5. `daari doctor` and `daari keys list` / `daari audit list --limit 5`.
6. Confirm spend / usage counts match the pre-backup baseline.

## Doctor

`daari doctor` emits an optional hint when no `*.tar.gz` (or encrypted
`.tar.gz.enc` / `.tar.gz.age`) newer than 7 days is found under
`~/.daari/backups/`. When recent backups exist but are all plaintext, doctor
suggests `--encrypt openssl`.

## Scheduled backups (#1216)

### Helm CronJob

The chart ships an optional CronJob (`backup.enabled`, default off). It runs
`daari backup create` on `backup.schedule` into a PVC, with `--encrypt openssl`
or `age` when `backup.encrypt` is set. Create the encrypt secret first:

```bash
kubectl create secret generic daari-backup \
  --from-literal=passphrase='use-a-long-secret'
```

```yaml
# values override
backup:
  enabled: true
  schedule: "0 2 * * *"
  encrypt: openssl
  retain: 7
  encryptSecret:
    name: daari-backup
    passphraseKey: passphrase
```

`backup.retain` keeps the newest N archives under `/backups` (0 disables prune).
See `deploy/helm/daari/values.yaml` for age recipient keys and PVC knobs.

### systemd user timer (non-Kubernetes)

Mirror the CronJob on a laptop / single-node install with a user timer (same
unit home as `daari service install`):

```bash
mkdir -p ~/.config/systemd/user ~/.daari/backups
# passphrase for openssl encrypt
mkdir -p ~/.config/daari
umask 077
printf '%s\n' 'use-a-long-secret' > ~/.config/daari/backup-pass
```

`~/.config/systemd/user/daari-backup.service`:

```ini
[Unit]
Description=daari encrypted backup

[Service]
Type=oneshot
Environment=DAARI_BACKUP_PASS_FILE=%h/.config/daari/backup-pass
ExecStart=/bin/sh -ec 'export DAARI_BACKUP_PASS="$(cat "$DAARI_BACKUP_PASS_FILE")"; daari backup create %h/.daari/backups/daari-$(date -u +%%Y%%m%%d%%H%%M%%S).tar.gz --encrypt openssl'
```

`~/.config/systemd/user/daari-backup.timer`:

```ini
[Unit]
Description=Daily daari backup

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now daari-backup.timer
systemctl --user list-timers daari-backup.timer
```

Prune old archives yourself (example: keep 7):
`ls -1t ~/.daari/backups/daari-*.tar.gz* | tail -n +8 | xargs -r rm -f`.

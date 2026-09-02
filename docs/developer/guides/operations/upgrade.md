# Upgrade and config migration

**Outcome:** Move a daari fleet from version N to N+1 in place, know what
survives, and roll back in one step if it does not.

daari has no vendor to call during an upgrade; this page is the upgrade
support. Every statement below cites the code that enforces it, so you can
verify it against the version you are about to install.

## Before you start

1. Read `CHANGELOG.md` and `docs/RELEASE-vX.Y.Z.md` for the target version.
   Breaking changes are called out there; there is no in-app migration wizard.
2. Note the running version: `pip show daari` (or `brew info daari`,
   `docker image inspect`, `helm get values`). There is no `daari --version`
   flag and `/health` returns only `{"status": "ok"}`
   (`daari/gateway/openai.py`, the `/health` route).
3. Back up `~/.daari/config.yaml` and the durable stores listed under
   [What survives](#what-survives-and-what-is-rebuilt). Caches can be skipped.
4. Run `daari doctor` and keep the output — it is your rollback baseline
   ([Doctor and health](doctor-health.md)).

## Upgrade steps

Configuration is read once at process start
(`Settings.load()` in `daari/config/settings.py`), so every path ends with a
restart of the daemon.

### pip / venv

```bash
source .venv/bin/activate
pip install --upgrade daari            # or: pip install -e ".[dev]" from a checkout
daari doctor
daari service restart
```

`daari service restart` runs `systemctl --user restart daari.service` on Linux
and `launchctl kickstart -k gui/$(id -u)/com.daari.gateway` on macOS (label
from `daari/setup/service.py`; it exits non-zero if `daari service install` was
never run). If you run `daari serve` by hand, stop and start it.
`scripts/install.sh` is safe to re-run: it recreates the venv, reinstalls, and
pulls only missing models; it never touches `~/.daari`.

### Homebrew

```bash
brew update && brew upgrade daari
daari doctor
daari service restart
```

The formula lives in the `naveenreddyalka/daari` tap
([Homebrew install](../../../setup/homebrew.md)).

### Docker / Compose

Images are published as `ghcr.io/naveenreddyalka/daari:vX.Y.Z`. State lives in
the `/home/daari/.daari` volume (`Dockerfile`), so a new image over the same
volume is an in-place upgrade:

```bash
docker compose pull daari
docker compose up -d daari
docker compose exec daari daari doctor
```

Pin an explicit tag in `docker-compose.yml`; `latest` makes rollback a guess.

### Helm

The chart is `deploy/helm/daari/`; the image tag is `image.tag` in
`values.yaml` and probes are `/health` (liveness) and `/ready` (readiness)
([Capacity and Helm](capacity-helm.md)):

```bash
helm upgrade daari deploy/helm/daari \
  --reuse-values --set image.tag=1.3.0 \
  --atomic --timeout 5m
```

`--atomic` rolls the release back automatically if new pods never pass
`/ready`. With two or more replicas behind Redis the default rolling update
keeps serving throughout; the L0/L1 stores are shared, so the new pods see the
same cache the old ones filled.

## Config compatibility policy

`~/.daari/config.yaml` is merged over the packaged `defaults.yaml`, then the
active project profile, then `DAARI_<SECTION>__<KEY>` environment variables,
and validated once by `Settings.model_validate()`
(`Settings.load()` in `daari/config/settings.py`). Consequences, all pinned by
tests in `tests/unit/test_settings.py`:

| Situation | Behaviour | Why |
|-----------|-----------|-----|
| Unknown **top-level** section (`typo_section: {}`) | Startup fails with `ValidationError: Extra inputs are not permitted` naming the key | `Settings` is a pydantic-settings `BaseSettings`, whose default is `extra="forbid"` (`test_unknown_top_level_key_fails_load`) |
| Unknown **nested** key (`server.future_option`) | Ignored silently; the rest of the section applies | Nested models are plain `BaseModel`s with the default `extra="ignore"` (`test_unknown_nested_key_is_ignored`) |
| Wrong type (`server.port: eleven`) | Startup fails with a `ValidationError` | Field types are enforced at load (`test_wrong_type_in_config_file_fails_load`) |
| Runtime setattr out of range | Rejected (`validate_assignment=True` on runtime models) | `test_setattr_rejects_*` |
| Legacy `org:` block | Merged into `enterprise:` and dropped | Shim in `Settings.load()`; `test_org_alias_block_maps_to_enterprise` |

What this means for an upgrade:

- **Downgrade-safe by design for nested keys.** A config written for N+1 that
  adds a new nested key still loads on N (the key is ignored). A *new top-level
  section* does not — remove it before rolling back.
- **Removed or renamed keys** are announced in `CHANGELOG.md`. Renamed keys
  keep a shim for at least one minor release (today: `org` → `enterprise`,
  `tenant_id` alias in `daari/enterprise/config.py`).
- **Validate before you restart.** There is no `daari config validate`
  subcommand and `daari doctor` only checks that the file exists and the
  port parses (`daari/setup/doctor.py`). Load the file explicitly:

```bash
python -c 'from daari.config.settings import Settings; Settings.load(); print("config ok")'
```

  A non-zero exit with `Extra inputs are not permitted` or a type error is the
  same failure the daemon would hit on start — fix it, then restart.

- **Fleet-pushed config** (`daari enterprise bootstrap`) merges the org block
  and any `routing` / `cache` / `frontier` / `guardrails` dicts into
  `config.yaml` with an atomic `0o600` write (`apply_org_config` in
  `daari/enterprise/bootstrap.py`, `daari/config/persist.py`). Runtime policy
  sync applies only the allow-listed keys in `SAFE_ROUTING_KEYS`,
  `SAFE_FRONTIER_KEYS`, `SAFE_CACHE_KEYS` plus `guardrails.enabled` and
  boundaries; unknown keys are ignored and a value of the wrong type is logged
  as `policy_sync_value_rejected` and skipped without aborting the sync
  (`daari/enterprise/policy_sync.py`).

## What survives, and what is rebuilt

Everything lives under `~/.daari/` (or the Docker volume / PVC). There is no
Alembic; every store creates its own tables with `CREATE TABLE IF NOT EXISTS`
on first open and, where the schema has changed, migrates in place on that
same open.

| Store | Location | Across an upgrade |
|-------|----------|-------------------|
| L0 exact cache | `~/.daari/cache/l0` (diskcache) or Redis `daari:l0:*` | **Survives.** Keys are a SHA-256 of messages, model, temperature, tools, tier and sampling (`daari/cache/exact.py`). Safe to delete; it refills. |
| L1 semantic cache | `~/.daari/cache/l1` (diskcache) or Redis `daari:l1:entries` | **Survives**, keyed by model/temperature/tools/tier (`daari/cache/semantic.py`). The embedding model name is *not* part of the key: if you change `cache.l1.embedding_model`, delete the L1 directory (or the Redis key) or old vectors will score ~0 and never hit. Unreadable entry lists are treated as empty, not fatal. |
| Org shared cache | `~/.daari/org/<id>/shared-cache/` | Survives; same rebuildable semantics (`daari/enterprise/service.py`). |
| Usage ledger | `~/.daari/usage/ledger.sqlite3` | **Durable.** Tables rebuilt in place when a pre-#156 schema is found (`UsageLedger._migrate`, `daari/observability/usage.py`). If init fails the ledger disables itself rather than crashing the gateway. |
| Virtual keys / teams | `~/.daari/auth/virtual-keys.sqlite3` | **Durable.** Additive `ALTER TABLE … ADD COLUMN` migrations (`_migrate` in `daari/auth/virtual_keys.py`). Back this up — keys cannot be regenerated. |
| Rate-limit counters | `rate-limit.sqlite3` / Redis `daari:rl:*` | Ephemeral; windows expire. |
| Traces, Responses API objects | `~/.daari/traces/` | Durable, create-if-missing only. |
| Audit log | `~/.daari/audit/audit.sqlite3` | Append-only, durable (`daari/enterprise/audit.py`). Back up for compliance. |
| Feedback / training examples | `~/.daari/feedback/`, `~/.daari/training/` | Durable, create-if-missing only. |
| Postgres (`observability.backend=postgres`) | `usage`, `client_usage`, `traces` | Create-if-missing on connect; on failure the store disables itself (`daari/observability/postgres_usage.py`). No destructive migrations are ever run against Postgres. |
| Request log | `~/.daari/cursor-requests.log` | Rotated per `observability.request_log_*`; disposable. |

Rule of thumb: **caches and counters are disposable, `.sqlite3` files are
not.** A backup of `~/.daari/config.yaml`, `auth/`, `usage/`, `audit/` and
`feedback/` is a complete backup.

Migrations are forward-only. A ledger rebuilt by N+1 still opens on N (the
extra `model`/token columns are ignored by older `INSERT`s); a virtual-keys
database with added columns likewise. Nothing in the tree drops columns.

## Rollback

1. Stop the daemon (or scale the deployment to the previous tag).
2. Reinstall the previous version:
   `pip install daari==X.Y.Z` · Homebrew has no versioned formula, so
   `brew uninstall daari` then `pip install daari==X.Y.Z` in a venv (or
   reinstall the formula from the tap commit for that release) ·
   `docker compose up -d` with the previous tag ·
   `helm rollback daari <REVISION>` (`helm history daari` lists them).
3. Restore `~/.daari/config.yaml` from your backup **if** the new version
   added a top-level section (older code forbids unknown top-level keys, see
   above). Nested additions can stay.
4. Leave the `.sqlite3` stores in place — migrations are additive. Only if the
   release notes say otherwise, restore them from backup.
5. Start, then `daari doctor` and compare with the baseline you saved.

Caches never need rolling back; if in doubt `rm -rf ~/.daari/cache` and let
them refill.

## Fleet ordering and version skew

A typical fleet is an org gateway (Helm/Docker, Redis + Postgres) plus daari on
developer laptops that pull policy from it.

1. **Gateway first, then laptops.** The policy-sync protocol is a signed JSON
   object (`X-Daari-Signature`, HMAC-SHA256 of the body —
   `daari/enterprise/bootstrap.py`) with no schema-version field. Laptops
   ignore keys they do not recognise, so a newer gateway can publish new keys
   before laptops upgrade; the reverse (new laptop, old gateway) simply sees
   fewer keys. Either direction is tolerated; gateway-first means new policy
   is live the moment laptops upgrade.
2. **Shared Redis/Postgres tolerate mixed versions.** L0/L1 entries are
   version-agnostic (see the table); Postgres tables are create-if-missing.
   Run mixed replicas during a rolling update without draining the cache.
3. **Rotate the signing secret only after both sides are upgraded** if a
   release changes the signature scheme; the release notes will say so.
4. **Laptops upgrade independently.** Each laptop is its own install; use the
   pip/brew steps above (or your MDM). A laptop that fails config validation
   on start is loud (`ValidationError`), not silently degraded.

## Verify

```bash
daari doctor
curl -fsS http://127.0.0.1:11435/ready
daari report          # ledger still has history → durable stores survived
```

## Next

→ [Doctor and health](doctor-health.md) · [Capacity and Helm](capacity-helm.md)
· [Releasing](../../../RELEASING.md) (how the versions you consume are cut)

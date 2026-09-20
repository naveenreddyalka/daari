# Org shared cache

**Outcome:** Run a shared cache/learning service for multiple daari daemons.

## Steps

```bash
docker compose --profile org up
# or
daari org-cache serve --host 0.0.0.0 --port 11436
```

Point clients via enterprise / org settings (cache URL + token). Fleet bootstrap:

```bash
daari enterprise bootstrap --org-config <signed-url>
```

## Verify

`GET http://127.0.0.1:11436/health`; after local L0 miss, traces may show org cache tiers.

## Invalidate, clear, and prune

Three different operations:

| Command | What it drops |
|---------|----------------|
| `daari cache invalidate --model <served>` | L0 rows whose cached response model matches, and L1 rows whose `context_key` starts with that model. |
| `daari cache invalidate --hash <id>` | Drops one L0 key or one L1 `answer_hash`. |
| `daari cache invalidate --team <id>` | L0 rows stored with `scope: team:<id>` and L1 rows whose `context_key` contains that segment. Admin JSON: `{"team_id": "<id>"}`. |
| `daari cache invalidate --key <id>` | L0 rows stored with `scope: key:<id>` and L1 rows whose `context_key` contains that segment. Admin JSON: `{"key_id": "<id>"}`. |
| `daari cache invalidate` (no flags) | Drops every L0 and L1 entry. Hits the running daemon (`POST /v1/daari/cache/invalidate`) when `daari serve` is up; otherwise edits the on-disk caches. Selectors can be combined; the daemon accepts `model`, `hash`, `team_id`, and `key_id` in the JSON body. |
| `daari context clear` | Deletes the L0, L1, and command-context directories entirely, then asks the daemon to reopen handles. |
| `daari cache prune` | Removes only TTL-expired disk entries. When `cache.backend` is Redis, prune does not scan — Redis expiry is the key TTL, and the command says so. |

## Next

→ [Capacity and Helm](../operations/capacity-helm.md) · [ADR-0014](../../../adr/0014-enterprise-distributed-org-learning.md)

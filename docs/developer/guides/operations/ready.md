# GET /ready

**Outcome:** A laptop process supervisor or a Helm probe can trust one
readiness contract.

`GET /ready` is the readiness probe. `GET /health` stays liveness: it returns
`{"status":"ok"}` when the process is listening and is not the same probe.

## Status values

| `status` | HTTP | Meaning |
|----------|------|---------|
| `ready` | 200 | Cache handle is present and the model backend check is `ok`. |
| `degraded` | 200 | The process can serve, but an optional dependency is down (some local pool hosts, or Redis/Postgres when those stores are configured). |
| `not_ready` | 503 | Cache is missing, no serving model host, or a local SQLite file is behind `STORE_SCHEMA_VERSIONS` (`schema_ok` false). |
| `shutting_down` | 503 | Coordinated shutdown. Load balancers should stop sending traffic. |

## Checks

The JSON body includes `checks`:

- `cache` — `ok` when a cache handle exists, otherwise `missing`.
- `model_backend` — local pool or Ollama/MLX probe (`ok` when the serving host answers).

Optional keys appear only when that store is configured:

- `redis` — when `cache.backend=redis`.
- `postgres` — when a Postgres store URL is configured.

`schema_ok` is a separate boolean. A failed schema check forces `not_ready` with HTTP 503.

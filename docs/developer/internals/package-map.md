# Package map

## `daari/` (Python)

| Module | Purpose |
|--------|---------|
| `server/` | FastAPI app, middleware, lifespan / `AppContext` |
| `cli/` | Typer CLI |
| `gateway/` | Wire adapters, guardrails, boundaries, PII, logging |
| `router/` | Tier selection, Ollama/MLX/frontier executors |
| `cache/` | L0/L1 (disk/Redis), normalize, CCS |
| `rules/` | L2 transforms, L2-dev matchers |
| `tools/` | Lt shell executor |
| `policy/` | Lt allow/deny/ask |
| `providers/` | Integration + live sources + MCP egress |
| `auth/` | Virtual keys |
| `config/` | Settings merge, project profiles, persist |
| `observability/` | Metrics, ledger, traces, Prometheus, OTel, Postgres |
| `learning/` | Feedback, tuner, finetune, propose-defaults |
| `enterprise/` | Org cache/learning, SSO, RBAC, audit, bootstrap |
| `clients/` | One-click setup recipes |
| `setup/` | Doctor, wizard, tunnel helpers |

## `packages/`

| Package | Purpose |
|---------|---------|
| `web-ui/` | Static dashboard (`daari web-ui serve`) |
| `browser-extension/` | MV3 popup → local daemon |

Routing logic never lives in `packages/` — only the Python daemon routes.

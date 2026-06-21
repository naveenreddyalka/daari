# Web UI Architecture (MVP)

## Goals

- Keep the UI read-only and low-complexity.
- Avoid extra build tooling for first release.
- Visualize core daemon counters quickly on localhost.

## Runtime

- Served by `daari web-ui serve`.
- CLI creates a tiny FastAPI app with:
  - `/web-ui-config.js` for runtime API base URL injection
  - static file mount from `packages/web-ui/`
- Browser fetches:
  - `GET /v1/daari/stats` (required)
  - `GET /v1/org-learning/profile` (best effort)

## Data contract assumptions

- `/v1/daari/stats` returns:
  - `total_requests` number
  - `errors` number
  - `tiers` object keyed by tier names with `count`, `p50_ms`, `p95_ms`
- `/v1/org-learning/profile` returns an object with `metrics` when enterprise learning is enabled.

## Future expansion

- Replace static JS with React/Vite only if interaction complexity grows.
- Add charting library once comparative timelines are needed.
- Add auth-aware headers if org services require tokens from browser context.

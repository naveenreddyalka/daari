# daari v1.1.0 Release Notes

> Date: 2026-06-20  
> Scope: Enterprise E2 + E3 delivery and web-ui MVP

## Highlights

- **Enterprise E2 org shared cache service**
  - Added `daari org-cache serve` service with `/v1/org-cache/get`, `/put`, `/stats`
  - Router now supports org-aware shared-cache lookup (`L0-org`, `L1-org`) and write-through
  - Added auth/token support and doctor checks for org-cache reachability

- **Enterprise E3 org learning**
  - Added feedback ingestion endpoint: `POST /v1/org-learning/feedback`
  - Added profile read/override endpoints: `GET/PUT /v1/org-learning/profile`
  - Added CLI operations: `daari org-learning stats`, `daari org-learning export`
  - Router consumes learned profile at startup (`prefer`, `confidence_threshold`)

- **Web UI MVP**
  - Added `daari web-ui serve` command
  - Ships static dashboard under `packages/web-ui/` for daemon stats and optional org-learning metrics
  - Includes architecture/readme docs and CLI smoke coverage

## Test status

- `pytest`: **122 passed, 1 skipped** (v1.0 baseline: 121 passed)
- Integration marker (`-m integration`): pass
- Benchmark marker (`-m benchmark`): pass
- Demo + bench scripts: pass

## Upgrade notes from v1.0

- Existing `daari serve` usage is unchanged.
- New optional commands:
  - `daari org-cache serve --org <org-id>`
  - `daari org-learning stats`
  - `daari org-learning export`
  - `daari web-ui serve`
- If upgrading org deployments, set or review:
  - `enterprise.org_id` (or `DAARI_ORG_ID`)
  - `enterprise.shared_cache_url` / `enterprise.shared_cache_token`
  - `enterprise.learning_url` / `enterprise.learning_token`
- `docs/RELEASE-v1.0.md` remains valid for baseline v1.0 install and local-first routing behavior.

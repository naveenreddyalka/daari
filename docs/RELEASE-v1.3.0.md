# Release notes — v1.3.0 (Gateway Completeness, Hardening & Relicense)

> Date: 2026-08-17  
> Scope: everything merged since v1.2.0 — 51 commits: full agent gateway surface, distributed limits, backend pooling, real token accounting, and a license change

## Summary

daari's gateway now covers the **full agent surface** (complete Responses API,
a real MCP JSON-RPC server, embeddings, vision, native Anthropic egress),
**holds up under multi-replica production load** (Redis-backed RPM/TPM rate
limits, health-checked local backend pools with circuit breakers, an
optimistic-locking fix for the shared Redis L1 cache), and **accounts for
usage truthfully** (provider-reported token counts, per-model per-direction
pricing, budgets charged to the key that spent them).

**License change:** starting with this release daari is licensed under
**PolyForm Noncommercial 1.0.0** — free for personal, educational, research,
and other noncommercial use; commercial use requires a separate license
(contact naveenreddy.alka@gmail.com). Releases through v1.2.0 remain
available under Apache 2.0.

## Highlights

### Gateway surface completion

| Feature | Detail |
|---------|--------|
| Responses API for agents (#196) | Background mode, `previous_response_id` chaining, response store, streaming events — the OpenAI agent loop works end to end |
| MCP server (#195) | Real JSON-RPC server at `POST /mcp`: `tools/list`, `tools/call` through the gateway |
| Embeddings (#193) | `POST /v1/embeddings` on the OpenAI surface |
| Vision + sampling (#192, #187) | Image parts survive routing; `temperature` / `top_p` / friends honored instead of dropped |
| Native Anthropic egress (#194) | L6 speaks `/v1/messages` directly — no lossy OpenAI-format round-trip for Claude |

### Reliability & scale-out

| Feature | Detail |
|---------|--------|
| Distributed rate limiting (#197 / #169) | RPM + TPM per key and per model, Redis or SQLite counters, global in-flight cap with bounded queue, `X-RateLimit-*` headers, limits in `/metrics` |
| Local backend pool (#198 / #170) | Multiple Ollama/MLX hosts per tier: background health probes, least-outstanding or round-robin pick, per-host circuit breakers, `degraded` `/ready`, `daari_meta.backend_id` |
| Redis L1 lost-update fix (#199 / #150) | `WATCH`/`MULTI` optimistic locking — concurrent replica writes both survive |
| Stream hardening (#175, #177, #185) | Boundaries, guardrails, and L6 escalation enforced on streams; deterministic tiers and frontier SSE relay; bounded-backoff retries for transient upstream failures |

### Correctness & accounting

| Feature | Detail |
|---------|--------|
| Real token accounting (#178) | Provider-reported token counts; price per model per direction |
| Trusted L1 hits (#179) | Semantic cache hits verified before serving |
| Budget attribution (#184) | Virtual-key budgets charged to the key that actually spent them |
| Test isolation (#186) | Suite no longer touches the real `~/.daari`; Redis L1 flake fixed |

### Also in this release

- Product boundaries / scope gate (Roadmap F6), triple-verified
- Developer documentation overhaul under `docs/developer/` (MkDocs site)
- Roadmap v2 F1–F5: Docker/compose, frontier pool, guardrails, virtual keys, Prometheus/Grafana, OTel export, Redis L0 / Postgres ledger, Helm, SSO/RBAC tracers, live-source providers
- Redis L1 shared cache backend (#135), Redis+Postgres compose profile (#142), web UI Bearer auth (#141), OIDC JWKS admin SSO (#136)
- PyPI packaging unblocked with trusted publisher; guided publish runner (#183); generated Homebrew formula (#182)

## Validation

- Default suite: **958 passed** (`pytest -m "not integration and not benchmark"`), 4 CI checks green on `main`
- Boot smoke: `/health`, `/ready` (degraded-state reporting), `/metrics` (rate-limit + backend-pool series), `/v1/models`
- Git history: all commits authored under a single personal identity; contributor graph verified clean

## Upgrade notes

- **License:** if you use daari commercially, v1.2.0 is the last Apache 2.0 release; contact the maintainer for commercial terms before upgrading.
- `rate_limit.*` settings are new and off by default aside from sane concurrency defaults; virtual-key `--rpm` / `--tpm` override globals.
- `routing.local_pool.backends` is optional — an empty list preserves the single `ollama.base_url` behavior.

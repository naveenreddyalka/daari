# daari — Project Context

> Handoff document for any tool or session picking up this project.  
> **Last updated:** 2026-07-23  
> **Project location:** `~/Home/Daari`  
> **GitHub:** https://github.com/naveenreddyalka/daari

---

## Current phase

**v1.2.0 released (2026-07-23) — Learning, Trust & Clients.** Roadmap v1 Phases A–E are all shipped at least to tracer depth: full tier chain (L0/L1/CCS/L2/Lt/L3–L6), prompt intelligence + traces + savings ledger, trust trains (false-hit measurement, prompt-cache passthrough, latency-aware + learned routing, budgets/PII scrub), Phase D learning (feedback → tuner → MLX fine-tune → deploy, opt-in D3 stats export), one-click clients (Cursor BYOK, Claude Code with full tool passthrough, JetBrains via Ollama facade, VS Code), per-project `.daari.yaml` profiles, gateway API-key auth, MLX backend, org shared cache/learning (E2/E3 tracer).

**Forward plan:** [docs/prd/ROADMAP-v2.md](docs/prd/ROADMAP-v2.md) — OSS launch readiness (Docker, PyPI, docs site), gateway parity (Responses API, guardrails, virtual keys, L6 fallback chains), Prometheus/OTel observability, and enterprise scale-out (Redis/Postgres backends, stateless replicas, Helm, org inference pool, fleet bootstrap, SSO/RBAC).

**Autonomous dev loop:** the project develops itself — backlog is GitHub issues labeled `auto-dev`, agents follow [AGENTS.md](AGENTS.md), `main` is protected (4 CI checks, auto-merge on green), a local launchd watchdog redeploys + runs live E2E every 2h and files regression issues. Runbook: [docs/AUTOMATION.md](docs/AUTOMATION.md). Repo is **public**.

**Last verified:** 535 pytest passing (2026-07-23); run `pytest` on current branch.

## What daari is

Open-source **local cost optimizer** — routes work through cache → tools → local AI before frontier.

**Tracking:** [TRACKING.md](docs/TRACKING.md)

**Docs:** [ARCHITECTURE](docs/ARCHITECTURE.md) · [PRD v0.4](docs/prd/PRD.md) · [TRACKING](docs/TRACKING.md) · [Phase A plan](docs/plans/phase-a.md) · [ROADMAP](docs/prd/ROADMAP.md) · [DEVELOPING](docs/DEVELOPING.md)

## Decisions made

| Topic | ADR / doc |
|-------|-----------|
| Frontier fallback | [0001](docs/adr/0001-frontier-fallback-policy.md) auto-escalate |
| Primary API | [0002](docs/adr/0002-openai-compatible-api.md) OpenAI-compat |
| Tool-native tier | [0003](docs/adr/0003-tool-native-tier.md) Lt |
| Agent tool_calls | [0004](docs/adr/0004-agent-tool-call-compatibility.md) |
| Tech stack | [0005](docs/adr/0005-python-tech-stack.md) Python 3.12 |
| Security | [0006](docs/adr/0006-local-daemon-security.md) localhost default |
| Gateway adapters | [0007](docs/adr/0007-pluggable-gateway-adapters.md) |
| L2-dev + CCS | [0008](docs/adr/0008-developer-command-rules-and-context-cache.md) |
| Integration providers | [0011](docs/adr/0011-pluggable-integration-providers.md) |
| Execution policy | [0012](docs/adr/0012-execution-policy.md) |
| Enterprise (Phase E) | [0014](docs/adr/0014-enterprise-distributed-org-learning.md) · [enterprise.md](docs/prd/enterprise.md) |
| Monorepo | [0013](docs/adr/0013-monorepo-structure.md) |
| Routing | [routing-spec](docs/prd/routing-spec.md) |
| Setup | [setup-spec](docs/prd/setup-spec.md) |

## Repo structure

**Single monorepo** — [ADR-0013](docs/adr/0013-monorepo-structure.md)

| Path | What |
|------|------|
| `daari/` | Python core (daemon, router, CLI) |
| `daari/clients/` | Setup recipes (Cursor, IntelliJ, etc.) — Phase A.1+ |
| `daari/setup/` | Doctor and setup helpers |
| `scripts/` | `install.sh` |
| `packages/` | TS/Kotlin surfaces later (extension, UI, IDE plugin) |
| `docs/` | PRD, ADRs, plans |
| `evals/` | Routing golden prompts |

**Separate repo:** `agent-skills` only — reusable skills, not daari runtime.

## Next tasks

The backlog lives in GitHub issues labeled `auto-dev`. The forward feature plan is
[ROADMAP-v2](docs/prd/ROADMAP-v2.md), in priority order:

1. **F1 — OSS launch readiness:** Docker/compose, readiness probes, PyPI publish (user-gated), MkDocs site, generated API/config reference, CHANGELOG, published benchmark
2. **F2 — Gateway parity:** OpenAI Responses API, L6 multi-provider fallback chains + key rotation + circuit breakers, guardrails, virtual keys, capability catalog
3. **F3 — Ops:** Prometheus `/metrics`, Grafana dashboard, optional OTel, web UI config editor
4. **F4 — Enterprise scale-out:** Redis cache backend, Postgres ledger, stateless replicas, Helm chart, org inference pool routing, fleet bootstrap, SSO/RBAC/audit
5. **F5 — Leftovers:** live-source providers (Open-Meteo/wttr.in/`sources.yaml`), MCP egress client, Phase B exit metrics, Homebrew

**Validation baseline (2026-07-23):**
- `pytest` (default suite): 535 passed, 1 skipped
- Live E2E (launchd watchdog every 2h + on-merge): Cursor-shaped OpenAI stream, Anthropic stream (`anthropic_stream_done` in `~/.daari/cursor-requests.log`), L0/L1 cache hits, `daari report`/`trace`
- Claude Code live: `claude -p` verified end-to-end through daari (trailing-system fix #94/#95)

**Pickup on new machine:** [docs/DEVELOPING.md](docs/DEVELOPING.md)

## Related repos

| Repo | Role |
|------|------|
| [`naveenreddyalka/daari`](https://github.com/naveenreddyalka/daari) | This project |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable agent skills |

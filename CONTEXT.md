# daari — Project Context

> Handoff document for any tool or session picking up this project.  
> **Last updated:** 2026-06-23  
> **Project location:** `~/Home/Daari`  
> **GitHub:** https://github.com/naveenreddyalka/daari

---

## Current phase

**v1.1.1 released; Cursor Ask E2E POC verified (2026-06-23)**  
Phase A/A.1/B/C3 baseline is complete with enterprise E2/E3, plus hot cache reload (`POST /v1/daari/reload-caches`), enterprise periodic profile sync (`org.learning_sync_seconds`), browser extension options UX, web UI export/theme controls, and Cursor tunnel-based E2E setup for BYOK/private-network restrictions.

**Cursor BYOK:** Ask + `daari` model works via cloudflared → local Ollama. Open items (tool hallucination on follow-ups, commit compat fixes, Ask vs Agent split) tracked in [TRACKING.md — Cursor E2E POC](docs/TRACKING.md#cursor-e2e-byok--poc-2026-06-23).

**Last verified:** run `pytest` on current branch.

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

## Next tasks (post-v1.1.0)

1. **Commit Cursor BYOK compat fixes** (content normalization, tools strip, stream L4 fallback, sanitization, tests) — see [TRACKING.md — Cursor E2E](docs/TRACKING.md#cursor-e2e-byok--poc-2026-06-23)
2. **Cursor follow-up quality** — reduce tool hallucination when IDE tools stripped but system prompt still describes tools
3. **Ask vs Agent BYOK split** — strip tools for Ask only; preserve tool round-trip for Agent per ADR-0004
4. **Org L1 semantic matching depth** in shared service (current tracer bullet is key-based)
5. **Lt B.1 profiles** (project/path command templates + richer confirmations)
6. Optional: enrich Anthropic stream usage accounting and preflight diagnostics
7. Browser extension E2E automation coverage (popup + options flow)

**L1 config** (`~/.daari/config.yaml`):

```yaml
cache:
  l1:
    enabled: true
    path: ~/.daari/cache/l1
    similarity_threshold: 0.88
    max_entries: 1000
    embedding_model: nomic-embed-text   # ollama pull nomic-embed-text
```

**Validation baseline (2026-06-23):**
- `pytest -m "not integration and not benchmark"`: 162 passed, 1 skipped
- Cursor Ask E2E (tunnel + daari model): verified — see [RELEASE-v1.1.2-cursor-e2e.md](docs/RELEASE-v1.1.2-cursor-e2e.md)
- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest -m integration`: 1 passed, 132 deselected
- `.venv/bin/python -m pytest -m benchmark`: 1 passed, 132 deselected
- `./scripts/demo.sh`: pass
- `./scripts/bench.sh`: pass
- `./scripts/smoke-cursor-dry-run.sh`: pass
- `scripts/tunnel.sh --setup-cursor`: manual smoke path (requires `cloudflared`)
- Manual smoke: org shared-cache cross-instance hit, org-learning feedback/profile sync (`daari org-learning sync`), `POST /v1/daari/reload-caches`, and `daari web-ui serve` dashboard load verified.

**Pickup on new machine:** [docs/DEVELOPING.md](docs/DEVELOPING.md)

## Related repos

| Repo | Role |
|------|------|
| [`naveenreddyalka/daari`](https://github.com/naveenreddyalka/daari) | This project |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable agent skills |

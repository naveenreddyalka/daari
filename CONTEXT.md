# daari — Project Context

> Handoff document for any tool or session picking up this project.  
> **Last updated:** 2026-06-20  
> **Project location:** `~/Home/Daari`  
> **GitHub:** https://github.com/naveenreddyalka/daari

---

## Current phase

**Phase B — Full local-first stack** (in progress)  
Phase A + A.1 complete; B.0 core now shipped: **L2 rules**, **L2-dev + CCS**, **Lt B.0**, **L4 tier**, no-frontier control, basic streaming SSE passthrough, ProviderRegistry executor wiring.

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
| `daari/clients/` | Setup recipes (Cursor, etc.) — Phase A.1+ |
| `daari/setup/` | Doctor and setup helpers |
| `scripts/` | `install.sh` |
| `packages/` | TS/Kotlin surfaces later (extension, UI, IDE plugin) |
| `docs/` | PRD, ADRs, plans |
| `evals/` | Routing golden prompts |

**Separate repo:** `agent-skills` only — reusable skills, not daari runtime.

## Next tasks (remaining Phase B / Phase C prep)

1. **`daari setup openai-compat`** recipe
2. **Lt B.1** confirmation UX + IntelliJ path + `daari context clear`
3. **L5 local tier** (Phase C1)
4. **Anthropic/MCP gateway adapters** (Phase C)
5. **Enterprise/provider plugins** rollout per ADR-0011

**L1 config** (`~/.daari/config.yaml`):

```yaml
cache:
  l1:
    enabled: true
    path: ~/.daari/cache/l1
    similarity_threshold: 0.92
    max_entries: 1000
    embedding_model: nomic-embed-text   # ollama pull nomic-embed-text
```

**Validation baseline (2026-06-20):**
- `pytest -m "not integration and not benchmark"`: pass
- `OLLAMA_HOST=http://127.0.0.1:11434 pytest`: pass
- `pytest -m benchmark`: pass
- `./scripts/demo.sh`: pass
- Manual tier smoke: L0/L1/L2/Lt/L3 verified; L4 override falls back to L3 when model unavailable; L6 requires API key.

**Pickup on new machine:** [docs/DEVELOPING.md](docs/DEVELOPING.md)

## Related repos

| Repo | Role |
|------|------|
| [`naveenreddyalka/daari`](https://github.com/naveenreddyalka/daari) | This project |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable agent skills |

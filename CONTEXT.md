# daari — Project Context

> Handoff document for any tool or session picking up this project.  
> **Last updated:** 2026-06-20  
> **Project location:** `~/Home/Daari`  
> **GitHub:** https://github.com/naveenreddyalka/daari

---

## Current phase

**Phase B.1 + Phase C1 depth** (in progress)  
Phase A + A.1 complete; B.0 core shipped: **L2 rules**, **L2-dev + CCS**, **Lt B.0**, **L4 tier**, no-frontier control. Current slice adds **setup all + IntelliJ setup**, **Lt ask/confirm UX**, **MCP minimal ingress**, **Sourcegraph/GHE token-gated minimal providers**, **L2-live URL fetch**, and **richer SSE metadata**.

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

## Next tasks (remaining Phase B / Phase C prep)

1. **Anthropic streaming + Claude Code setup** (`daari setup claude-code`)
2. **MCP ingress expansion** (tool schemas + richer typed responses)
3. **Provider depth** for Sourcegraph/GHE beyond token-gated minimal paths
4. **Lt B.1 profiles** (project/path command templates + richer confirmations)
5. Optional: improve bench script resilience when model path is unavailable

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
- `.venv/bin/python -m pytest`: 78 passed, 1 skipped
- `OLLAMA_HOST=http://127.0.0.1:11434 .venv/bin/python -m pytest -v`: 79 passed
- `.venv/bin/python -m pytest -m benchmark`: 1 passed, 78 deselected
- `./scripts/demo.sh`: pass
- `./scripts/bench.sh`: pass
- Manual tier smoke: setup `all`/`intellij` dry-runs, Lt ask/confirm flow, MCP endpoint, Anthropic adapter, and L0/L1/L2/Lt/L3 routes verified; L4/L5 override fallback behavior covered in tests; L6 requires API key.

**Pickup on new machine:** [docs/DEVELOPING.md](docs/DEVELOPING.md)

## Related repos

| Repo | Role |
|------|------|
| [`naveenreddyalka/daari`](https://github.com/naveenreddyalka/daari) | This project |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable agent skills |

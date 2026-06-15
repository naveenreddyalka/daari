# daari — Project Context

> Handoff document for any tool or session picking up this project.  
> **Last updated:** June 2026  
> **Project location:** `~/Home/Daari`  
> **GitHub:** https://github.com/naveenreddyalka/daari

---

## Current phase

**PRD draft v0.2** — universal tool support, tool-native tier, setup module added; awaiting review.

No application code yet.

## What daari is

An **end-to-end local execution router** that works with Cursor, Claude Code, any CLI/UI/IDE with minimal config change.

Routes each request through: **cache → rules → tool-native (no AI) → local models → frontier (last resort)**.

- **OpenAI-compatible API** — primary adapter so tools only change base URL ([ADR-0002](docs/adr/0002-openai-compatible-api.md))
- **Lt tool-native tier** — IntelliJ, git, linter, formatter when no AI needed ([ADR-0003](docs/adr/0003-tool-native-tier.md))
- **Setup module** — `install.sh`, `daari setup <tool>`, `daari doctor`

Full spec: [`docs/prd/PRD.md`](docs/prd/PRD.md)

## Decisions made

| Topic | Decision |
|-------|----------|
| Frontier fallback | Auto-escalate when local fails — [ADR-0001](docs/adr/0001-frontier-fallback-policy.md) |
| Primary API | OpenAI-compatible — [ADR-0002](docs/adr/0002-openai-compatible-api.md) |
| Non-AI execution | Lt tool-native tier — [ADR-0003](docs/adr/0003-tool-native-tier.md) |
| Language | **Pending** (Python vs Go) |

## Open decisions

1. Primary implementation language ([OD-2](docs/prd/PRD.md#open-decisions))
2. IntelliJ integration mechanism — CLI first recommended ([OD-5](docs/prd/PRD.md#open-decisions))
3. Install delivery — `install.sh` for MVP ([OD-6](docs/prd/PRD.md#open-decisions))

## First actions (every session)

1. Read this file
2. Read [`docs/prd/PRD.md`](docs/prd/PRD.md)
3. Do not implement until PRD approved

## Related repos

| Repo | Role |
|------|------|
| [`naveenreddyalka/daari`](https://github.com/naveenreddyalka/daari) | This project |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable agent skills |

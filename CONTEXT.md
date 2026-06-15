# daari — Project Context

> Handoff document for any tool or session picking up this project.  
> **Last updated:** June 2026  
> **Project location:** `~/Home/Daari`  
> **GitHub:** https://github.com/naveenreddyalka/daari

---

## Current phase

**PRD v0.4 review** — plan issues 18/18 resolved. Specs + ADRs complete. Awaiting PRD approval before implementation.

No application code yet.

## What daari is

Open-source **local cost optimizer** — routes work through cache → tools → local AI before frontier.

**Docs:** [PRD v0.4](docs/prd/PRD.md) · [plan review](docs/prd/PLAN-REVIEW.md) · [competitors](docs/discovery/04-competitive-landscape.md)

## Decisions made

| Topic | ADR / doc |
|-------|-----------|
| Frontier fallback | [0001](docs/adr/0001-frontier-fallback-policy.md) auto-escalate |
| Primary API | [0002](docs/adr/0002-openai-compatible-api.md) OpenAI-compat |
| Tool-native tier | [0003](docs/adr/0003-tool-native-tier.md) Lt |
| Agent tool_calls | [0004](docs/adr/0004-agent-tool-call-compatibility.md) |
| Tech stack | [0005](docs/adr/0005-python-tech-stack.md) Python 3.12 |
| Security | [0006](docs/adr/0006-local-daemon-security.md) localhost default |
| Routing | [routing-spec](docs/prd/routing-spec.md) |
| Setup | [setup-spec](docs/prd/setup-spec.md) |

## Next step

Approve PRD v0.4 → write Phase A implementation plan.

## Related repos

| Repo | Role |
|------|------|
| [`naveenreddyalka/daari`](https://github.com/naveenreddyalka/daari) | This project |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable agent skills |

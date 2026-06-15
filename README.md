# daari

> **Status:** Discovery & PRD phase  
> **Repo:** https://github.com/naveenreddyalka/daari

**Local execution router (e2e)** — works with Cursor, Claude Code, CLI, UI, IDE. Routes to cache, existing tools (IntelliJ/git/lint — no AI), local models, frontier last. OpenAI-compatible API + single-command setup per tool.

PRD v0.2: [`docs/prd/PRD.md`](docs/prd/PRD.md)

## What is here now

| Path | Purpose |
|------|---------|
| [`CONTEXT.md`](CONTEXT.md) | Agent handoff — read this first in any session |
| [`docs/PRD-PLAN.md`](docs/PRD-PLAN.md) | Plan for how we write the PRD (phases, deliverables, gates) |
| [`docs/discovery/`](docs/discovery/) | Working notes during discovery |
| [`docs/prd/`](docs/prd/) | Final PRD and requirements (when approved) |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records |

## Conventions

- **Docs live in this repo** — PRD, discovery notes, ADRs are versioned here.
- **Reusable agent skills live elsewhere** — see [Skills repo](#skills-repo) below.
- **Decisions get written down** — if we discuss it, we capture it in `docs/discovery/` or an ADR.

## Skills repo

Project-specific skills stay in this repo under `.cursor/skills/` (when needed).

**Cross-project, reusable skills** belong in a separate repo so other projects can install them:

- Intended location: `https://github.com/naveenreddyalka/agent-skills` *(create when first skill is ready)*

## Getting started (agents)

1. Read `CONTEXT.md`
2. Read `docs/PRD-PLAN.md` for current phase and next steps
3. Check `docs/discovery/` for latest notes
4. Do not write implementation code until PRD is approved

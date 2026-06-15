# ADR-0005: Python tech stack for MVP

Date: 2026-06-15  
Status: **accepted**

## Context

daari needs a primary implementation language (OD-2). Options evaluated in `docs/discovery/03-approach-options.md`. Plan review issue #9.

## Decision

**Python 3.12** for Phase A through Phase B implementation.

## Rationale

| Factor | Python | Go |
|--------|--------|-----|
| MVP velocity | ✅ Fast iteration | Slower |
| FastAPI OpenAI-compat | ✅ Mature | Build more |
| Embeddings / eval (L1, routing tests) | ✅ Rich ecosystem | Weaker |
| Ollama clients | ✅ httpx, ollama lib | Available |
| Daemon packaging | ⚠️ venv/pyinstaller | ✅ Single binary |
| Solo builder | ✅ One person, fewer files | More boilerplate |

**Trade-off accepted:** Packaging complexity over raw startup latency. daari is localhost-bound; 50ms vs 5ms startup is irrelevant.

## Stack

```
Python 3.12
├── FastAPI + uvicorn     # OpenAI-compat gateway
├── typer                 # CLI (serve, stats, setup, doctor)
├── httpx                 # Ollama + frontier HTTP
├── pydantic + pydantic-settings  # config
├── diskcache or sqlite3  # L0 cache
└── pytest                # routing eval + unit tests
```

**External dependency:** Ollama (user-installed, not bundled).

## Consequences

- ADR revisit if p99 latency or memory becomes problem at scale
- Optional Go rewrite of gateway only in v2 — router logic stays testable in Python
- CI: Python 3.12, pytest, optional Ollama integration job

## Not chosen (for now)

| Option | Reason deferred |
|--------|-----------------|
| Go | Better daemon story but slower ML/routing iteration |
| Rust | MVP velocity too slow |
| TypeScript | Weaker local embedding/eval path |

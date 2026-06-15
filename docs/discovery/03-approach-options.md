# Approach Options — daari

> **Status:** Draft — for Phase 3 decision  
> **Phase:** 3

---

## Product shape (recommended)

**Local daemon + OpenAI-compatible proxy + CLI**

| Option | Pros | Cons |
|--------|------|------|
| **A. Daemon + compat API** *(recommended)* | Drop-in for Cursor/tools; clear boundary | Must maintain API compatibility |
| B. Library/SDK only | Simple embed | Every tool needs custom integration |
| C. Full agent framework | Rich features | Scope explosion; overlaps Cursor |

**Recommendation:** A — daari is **infrastructure**, not an agent.

---

## Language options

### Option 1 — Python *(recommended for MVP speed)*

| Pros | Cons |
|------|------|
| Fast iteration; rich ML ecosystem (embeddings, eval) | GIL; less ideal if ultra-low-latency critical |
| Ollama clients, FastAPI, pydantic mature | Packaging/distribution slightly heavier |
| Easy eval harness and notebook prototyping | |

**Stack sketch:** Python 3.12, FastAPI, httpx → Ollama, SQLite + sqlite-vec or chromadb, typer CLI

### Option 2 — Go

| Pros | Cons |
|------|------|
| Single binary; great daemon story | Weaker embedding/eval ergonomics |
| Low memory, fast startup | Slower ML experimentation |
| Good HTTP server | |

**Stack sketch:** Go 1.22, chi/fiber, go-ollama client, embedded bbolt/SQLite

### Option 3 — Rust

| Pros | Cons |
|------|------|
| Performance, safety | Slowest MVP velocity |
| Excellent for production daemon | Embedding story more DIY |

**Verdict:** Consider for v2 rewrite if Python bottlenecks prove real — not MVP.

### Option 4 — TypeScript (Node/Bun)

| Pros | Cons |
|------|------|
| Familiar if frontend-heavy | Heavier runtime; ML libs thinner |
| Good for API gateway | Local embedding models awkward |

**Verdict:** Secondary choice if user prefers TS ecosystem.

---

## Local inference backend

| Backend | Role |
|---------|------|
| **Ollama** *(recommended MVP)* | Model serving; already local-friendly on macOS |
| llama.cpp direct | More control; more ops burden |
| MLX (Apple) | Best Apple Silicon perf; narrower model support |

**Recommendation:** Start Ollama; abstract `Executor` so MLX can plug in later.

---

## Cache & embeddings

| Component | MVP | v1 |
|-----------|-----|-----|
| Exact cache | SQLite or diskcache | Same |
| Semantic cache | Defer to v1 | sqlite-vec, chromadb, or fastembed + in-memory index |
| Embeddings model | — | small local model via Ollama (e.g. nomic-embed) |

---

## Recommended MVP stack

```
Python 3.12
├── FastAPI          # OpenAI-compat gateway
├── typer            # CLI
├── httpx            # Ollama client
├── diskcache/SQLite # L0 exact cache
├── pydantic         # config + schemas
└── Ollama           # L3+ inference (external)
```

**Decision pending your approval** → record in ADR-0001 when chosen.

---

## Deployment model

- Run as local daemon on `127.0.0.1:PORT`
- Optional launchd plist for macOS auto-start
- Config file: `~/.config/daari/config.yaml` or `./daari.yaml` in project

---

## Next step

Pick language (Python vs Go vs other) and frontier policy (OD-1 in PRD) → write ADR-0001.

# Phase A — Tracer bullet implementation plan

> **Status:** Ready to execute  
> **PRD:** v0.4 approved 2026-06-15  
> **Duration:** ~2–3 weeks  
> **Goal:** Prove L0 cache + L3 Ollama path end-to-end via OpenAI-compat gateway

---

## Exit criteria (from ROADMAP)

- [x] Second identical prompt hits **L0**
- [x] `daari stats` shows tier breakdown
- [~] Cursor works via [manual setup](../setup/cursor.md) — **deferred:** user smoke test on other device (not blocking Phase A)
- [x] 10 eval prompts (GP-01–GP-10) pass MVP criteria (`tests/test_routing_eval.py`)

---

## Project layout (monorepo)

```
daari/                    # repo root — single repo for all daari code
├── daari/                # Python package (brain) — Phase A starts here
├── packages/             # TS/Kotlin surfaces — Phase C+ (see packages/README.md)
├── evals/
├── docs/
├── scripts/              # install.sh — Phase A.1
└── pyproject.toml
```

Full spec: [ADR-0013](../adr/0013-monorepo-structure.md)

## Project layout (Python package — Phase A)

```
daari/
├── pyproject.toml
├── README.md                    # dev quickstart (keep root README high-level)
├── daari/
│   ├── cli/
│   ├── clients/              # setup recipes — stub until Phase A.1
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py          # pydantic-settings → ~/.daari/config.yaml
│   │   └── defaults.yaml
│   ├── gateway/
│   │   ├── __init__.py
│   │   ├── base.py              # GatewayAdapter protocol
│   │   ├── internal.py          # InternalRequest / InternalResponse
│   │   └── openai.py            # OpenAI-compat adapter (Cursor uses this at runtime)
│   ├── router/
│   │   ├── __init__.py
│   │   └── router.py            # Phase A: L0 → L3 only
│   ├── cache/
│   │   ├── __init__.py
│   │   └── exact.py             # L0 diskcache/SQLite
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py              # IntegrationProvider protocol
│   │   ├── registry.py          # ProviderRegistry
│   │   └── builtin/
│   │       ├── cache.py         # L0 provider wrapper
│   │       └── ollama.py        # L3 executor
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── metrics.py           # in-memory counters
│   │   └── logging.py
│   └── server/
│       ├── __init__.py
│       └── app.py               # FastAPI app factory
├── tests/
│   ├── conftest.py
│   ├── test_l0_cache.py
│   ├── test_router.py
│   ├── test_openai_gateway.py
│   └── test_routing_eval.py     # GP-01–GP-10
└── evals/routing/prompts.jsonl
```

---

## Dependencies (`pyproject.toml`)

```toml
[project]
name = "daari"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "typer>=0.12",
  "httpx>=0.27",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "diskcache>=5.6",
  "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.8"]

[project.scripts]
daari = "daari.cli.app:app"
```

**External:** Ollama (user-installed). Default model: `llama3.2:3b`.

---

## Task breakdown

### Week 1 — Scaffold + gateway + L0

| # | Task | Done when |
|---|------|-----------|
| A1 | **Scaffold** — `pyproject.toml`, package layout, `daari --help` | Typer app runs |
| A2 | **Config** — `Settings` loads `~/.daari/config.yaml`; defaults for host/port/model | Config round-trips in test |
| A3 | **Internal model** — `InternalRequest`, `InternalResponse`, `DaariMeta` | Types used by router |
| A4 | **L0 cache** — hash key per [routing-spec](../prd/routing-spec.md#l0-cache-key); diskcache store | Identical input → hit |
| A5 | **ProviderRegistry** — protocol + register cache/ollama stubs | `registry.get("ollama")` works |
| A6 | **OpenAI gateway** — `POST /v1/chat/completions` non-streaming | curl returns chat completion JSON |
| A7 | **FastAPI server** — bind `127.0.0.1:11435` per ADR-0006 | `daari serve` starts daemon |

### Week 2 — Router + Ollama + observability

| # | Task | Done when |
|---|------|-----------|
| A8 | **Ollama executor** — httpx to `localhost:11434/api/chat` | L3 response returned |
| A9 | **Router Phase A** — L0 check → else L3; log decision | `daari_meta.tier` correct |
| A10 | **Metrics** — counters per tier, latency_ms, cache_hit | In-memory store updated per request |
| A11 | **`daari stats`** — print tier breakdown table | CLI shows hits/misses |
| A12 | **Agent passthrough** — skip L0 if `tool_calls` in messages (ADR-0004) | GP-18 behavior stubbed/deferred to B if tools absent |
| A13 | **Headers** — honor `X-Daari-No-Cache`, `X-Daari-Tier-Override` | Tests pass |
| A14 | **Error handling** — Ollama down → clear 503 JSON | No silent hang |

### Week 3 — Evals + docs + manual Cursor validation

| # | Task | Done when |
|---|------|-----------|
| A15 | **Eval file** — populate `evals/routing/prompts.jsonl` GP-01–GP-10 | File matches routing-spec |
| A16 | **Routing eval test** — pytest loads jsonl, asserts MVP tiers | CI-local pass (mock Ollama optional) |
| A17 | **Integration test** — live Ollama if `OLLAMA_HOST` set; else skip | Mark `@pytest.mark.integration` |
| A18 | **Manual Cursor doc** — verify [cursor.md](../setup/cursor.md) steps | Doc matches actual port/fields |
| A19 | **Dev README** — install, serve, curl example, stats | New contributor can run in 5 min |
| A20 | **Stretch: streaming** — SSE for L3 if time; else document as deferred | ADR note in PRD already |

---

## Router logic (Phase A only)

```python
async def route(req: InternalRequest) -> InternalResponse:
    if req.has_tool_calls_in_history:
        return await ollama.execute(req)  # passthrough, no L0

    if not req.no_cache:
        hit = l0.get(req)
        if hit:
            metrics.record(tier="L0", cache_hit=True)
            return hit

    resp = await ollama.execute(req)  # always L3 in Phase A
    if not req.no_cache:
        l0.put(req, resp)
    metrics.record(tier="L3", cache_hit=False)
    return resp
```

No L1, L2, Lt, L6 in Phase A.

---

## API contract (minimal)

**Request:** standard OpenAI chat completion body.

**Response:** OpenAI shape + optional extension:

```json
{
  "choices": [{ "message": { "role": "assistant", "content": "..." } }],
  "model": "llama3.2:3b",
  "daari_meta": {
    "tier": "L0",
    "cache_hit": true,
    "executor": "cache",
    "provider_id": "cache",
    "latency_ms": 4,
    "model": null
  }
}
```

Clients that ignore unknown fields (Cursor) work unchanged.

---

## Config defaults (`~/.daari/config.yaml`)

```yaml
server:
  host: 127.0.0.1
  port: 11435

models:
  l3: llama3.2:3b

ollama:
  base_url: http://127.0.0.1:11434

cache:
  l0:
    enabled: true
    path: ~/.daari/cache/l0
    ttl_seconds: null  # no expiry MVP
```

---

## Test strategy

| Layer | Approach |
|-------|----------|
| Unit | L0 key hashing, router tier selection, config load |
| Gateway | httpx TestClient against FastAPI; assert OpenAI JSON shape |
| Eval | GP-01–GP-10 from jsonl; mock Ollama with fixed response |
| Integration | Optional live Ollama; manual Cursor smoke test |

**MVP eval pass:** GP-01/GP-05 → L0 on repeat; GP-02–04, 09, 17 → L3; no 5xx.

---

## Explicitly NOT in Phase A

Per PRD — do not scope-creep:

- L1, L2, L2-dev, L2-live, CCS, Lt, PolicyEngine
- L4, L5, L6 / frontier
- `install.sh`, `daari setup`, `daari doctor`
- Streaming (unless stretch)
- Anthropic gateway, MCP

---

## First implementation session (start here)

1. Run A1–A3: scaffold + config + internal types  
2. Run A4–A7: L0 + gateway + `daari serve`  
3. curl smoke test:

```bash
curl http://127.0.0.1:11435/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3.2:3b","messages":[{"role":"user","content":"Say hi"}]}'
```

4. Repeat same request → verify `daari_meta.tier == "L0"`

---

## Phase A.1 — Install & setup

> **Tracker:** [TRACKING.md](../TRACKING.md) · **ROADMAP:** [Phase A.1](../prd/ROADMAP.md#phase-a1--install--frontier-fallback)

### Subtasks

- [x] `scripts/install.sh` — venv, pip, Ollama pull (`13a2345`)
- [x] `daari doctor` — Python, config, Ollama, model, optional daemon
- [x] `daari setup cursor --dry-run` — planned diff without writes
- [x] `daari setup cursor` — apply patches + backup (`aaf3f06`)
- [x] `daari setup --undo cursor` — restore latest backup
- [x] `daari setup` — interactive wizard (Cursor / models / doctor)
- [x] `daari setup models` — pick Ollama model for L3 tier
- [ ] `daari install` — Typer parity with `install.sh` (ROADMAP; script works today)
- [ ] L6 frontier executor + confidence scoring (ADR-0001) — **deferred**
- [~] Cursor smoke test on device with Cursor installed — user-owned, non-blocking

### Exit criteria

- [~] `./install.sh && daari doctor` passes on fresh clone
- [x] `daari setup cursor --dry-run` shows diff
- [ ] Low-confidence local response escalates to L6 (if keys configured)

---

## After Phase A

→ Phase A.1 above; then Phase B (L1, L2, Lt, …)

# daari — Product Roadmap (v1 — shipped)

> **Status:** Complete — Phases A–E shipped (some at tracer depth); superseded by [ROADMAP-v2.md](ROADMAP-v2.md) for forward work  
> **Last updated:** 2026-07-23  
> **Purpose:** Historical phase plan — what shipped when; per-task status lives in [TRACKING.md](../TRACKING.md)
>
> **Known deviations from this plan:** C1 live-source providers (Open-Meteo/wttr.in/`sources.yaml`) and the MCP egress client moved to [ROADMAP-v2 Train F5](ROADMAP-v2.md); the IntelliJ Kotlin plugin was superseded by the Ollama-compatible facade; L5 (`llama3.1:70b`) is wired but the model pull stays user-optional; D4 depends on D3 opt-in adoption.

---

## Gateway adapter architecture

daari is **not tied to OpenAI's API shape**. Gateways are pluggable ([ADR-0007](../adr/0007-pluggable-gateway-adapters.md)):

```
Client → [Adapter: openai | anthropic | mcp | …] → InternalRequest
              → Router (L0–L6, Lt) → InternalResponse → Adapter → Client
```

| Phase | Adapters shipped |
|-------|------------------|
| A | `openai` only |
| C1 | `mcp`, optional `daari-native` |
| C2 | `anthropic` (Claude Code) |

Python module layout (Phase A must allow this):

```
daari/gateway/
  base.py       # GatewayAdapter protocol
  internal.py   # canonical request/response
  openai.py     # Phase A
  anthropic.py  # stub until C2
```

---

## Language strategy (overall)

| Layer | Language | Why | When |
|-------|----------|-----|------|
| **Core** (daemon, router, cache, CLI) | **Python 3.12** | FastAPI, routing, eval, Ollama — [ADR-0005](../adr/0005-python-tech-stack.md) | Phase A → B |
| **Install script** | **Bash** | `./install.sh` — venv, deps, Ollama pull | Phase A.1 |
| **Setup recipes** | **Python** (Typer) | Patch client configs; cross-platform logic | Phase A.1 → B |
| **Eval / tests** | **Python** (pytest) | Golden prompts, routing regression | Phase A → B |
| **Web UI** (optional) | **TypeScript** (future) | Dashboard for stats/cache — talks to localhost API | Phase C1+ |
| **IntelliJ plugin** (optional) | **Kotlin/Java** (future) | Native IDE integration if CLI insufficient | Phase C2+ |
| **MCP server** | **Python** (likely) | Reuse router modules | Phase C1 |

**Rule:** One Python **brain**. Other languages only for client-specific surfaces — never duplicate routing logic.

---

## Client support roadmap

| Client | Role | Wire format | Setup | Language (daari side) | Phase |
|--------|------|-------------|-------|----------------------|-------|
| **Cursor** | AI IDE client | OpenAI-compat | Manual doc → `daari setup cursor` | Python + bash | A → A.1 |
| **curl / scripts** | Testing | OpenAI-compat | None | — | A |
| **OpenAI SDK** (Python/TS) | Custom scripts | OpenAI-compat | `daari setup openai-compat` (env vars) | Python | B |
| **Claude Code** | CLI agent | Anthropic-compat *(needed)* | `daari setup claude-code` | Python gateway | C2 |
| **IntelliJ IDEA** | Lt backend (not AI client) | Subprocess / CLI | `daari setup intellij` | Python spawns IDE CLI | B.1 → C2 |
| **VS Code** | Lt backend (future) | CLI / extensions | `daari setup vscode` | Python | C2+ |
| **Generic UI** | Future dashboard | REST → daari API | N/A | TypeScript (UI only) | C1+ |
| **MCP agents** | Agent introspection | MCP protocol | Bundled in daemon | Python | C1 |

---

## Phase A — Tracer bullet MVP

**Duration:** ~2–3 weeks  
**Goal:** Prove cache + local model path works end-to-end  
**Language:** Python 3.12 only

### Ships

| Component | Tech | Details |
|-----------|------|---------|
| HTTP gateway | FastAPI + uvicorn | `POST /v1/chat/completions`, port `11435` |
| L0 exact cache | diskcache or SQLite | Hash(prompt + params) |
| Model executor | httpx → Ollama | Single model, e.g. `llama3.2:3b` |
| Router | Python heuristics | Logged; all requests → L3 unless L0 hit |
| **ProviderRegistry** | Protocol + empty registry | cache + ollama providers only — [ADR-0011](../adr/0011-pluggable-integration-providers.md) |
| CLI | Typer | `daari serve`, `daari stats` |
| Config | pydantic-settings | `~/.daari/config.yaml` |
| Eval | pytest + 10 prompts | From [routing-spec](routing-spec.md) GP-01–GP-10 |
| Docs | Markdown | [docs/setup/cursor.md](../setup/cursor.md) manual setup |

### Clients supported

| Client | Support level |
|--------|---------------|
| Cursor | ✅ Manual setup doc |
| curl / OpenAI SDK | ✅ base_url |
| Claude Code | ❌ |
| IntelliJ | ❌ |
| Agent tool_calls | ⚠️ Passthrough per ADR-0004; no L0 cache |

### Does NOT ship

- L1, L2, Lt, L4, L5, L6
- `daari setup`, `install.sh`, `daari doctor`
- Streaming (optional stretch — document if cut)

### Exit criteria

- [x] Second identical prompt hits L0
- [x] `daari stats` shows tier breakdown
- [x] Cursor works via manual config
- [x] 10 eval prompts pass

---

## Phase A.1 — Install & frontier fallback

**Duration:** ~1 week  
**Goal:** One-command install; quality fallback when local weak  
**Language:** Python + bash

### Ships

| Component | Tech |
|-----------|------|
| `install.sh` | bash — venv, pip install, Ollama model pull |
| `daari install` | Python Typer — same as script |
| `daari setup cursor` | Python — patch settings + backup |
| `daari setup --undo` | Python — restore backup |
| `daari doctor` | Python — health checks |
| L6 executor | httpx → OpenAI/Anthropic | Per ADR-0001 auto-escalate |
| Confidence scoring | Python | Per [routing-spec](routing-spec.md) |

### Clients supported

| Client | Support level |
|--------|---------------|
| Cursor | ✅ Automated setup |
| Claude Code | ❌ (still needs Anthropic gateway) |

### Exit criteria

- [x] `./install.sh && daari doctor` passes
- [x] `daari setup cursor --dry-run` shows diff
- [x] Low-confidence local response escalates to L6 (if keys configured)

---

## Phase B — Full local-first stack (v1)

**Duration:** ~4–6 weeks  
**Goal:** Semantic cache, rules, Lt CLI tools, multi-model, multi-client setup  
**Language:** Python 3.12 (+ bash for any shell helpers)

### B.0 — Cache, rules, L2-dev, CCS, Lt CLI, execution policy

| Component | Tech |
|-----------|------|
| L1 semantic cache | sqlite-vec + Ollama embeddings |
| L2 rules engine | Python regex/templates |
| **L2-dev** | Developer command patterns |
| **CCS** | Command context store in `~/.daari/context/` |
| **PolicyEngine B.0** | Allowlist + blocklist + default deny unknown — [ADR-0012](../adr/0012-execution-policy.md) |
| **CCS policy** | TTL, sensitive skip, redaction, size limits |
| **Lt B.0** | Python subprocess → git, eslint, prettier, **shell from L2-dev** |
| L4 medium model | Second Ollama model (e.g. `llama3.1:8b`) |
| Hybrid classifier | Heuristics + optional SLM |
| `daari setup openai-compat` | Python — print/export env vars |
| Eval expansion | 20 prompts GP-01–GP-20 |

### B.1 — Lt IDE + confirmation + project commands

| Component | Tech |
|-----------|------|
| **Lt B.1** | Python subprocess → **IntelliJ** `idea` CLI |
| **PolicyEngine B.1** | Confirmation gate (`X-Daari-Confirm-Tool`), `.daari/commands.yaml` merge |
| **`daari context clear`** | Invalidate CCS for repo/command |
| `daari setup intellij` | Python — register IDE path in config |

### Clients supported (end of Phase B)

| Client | Support | daari language | Notes |
|--------|---------|----------------|-------|
| Cursor | ✅ Full | Python setup | OpenAI-compat |
| OpenAI SDK | ✅ Full | Python setup | env vars |
| IntelliJ | ✅ Lt backend | Python spawns CLI | Not an AI client |
| Claude Code | ⚠️ Partial | — | Only if user forces OpenAI-compat mode |
| VS Code | ❌ | — | Phase C2 |

### Exit criteria

- [ ] `$0 tier rate` ≥30% on dev session eval — *not formally measured; queued in [ROADMAP-v2 F5](ROADMAP-v2.md)*
- [x] Lt dispatches `git status` without model call
- [ ] Routing accuracy ≥90% on 20-prompt eval — *eval suite passes; the accuracy metric itself queued in [ROADMAP-v2 F5](ROADMAP-v2.md)*
- [x] `daari setup --all` detects Cursor + Ollama

---

## Phase C1 — Agent, live sources & integration foundation (v2a)

**Duration:** ~3–4 weeks  
**Goal:** L2-live + Lt-fetch, MCP client, provider plugins, profiles  
**Language:** Python (+ TypeScript if UI started)

| Component | Tech |
|-----------|------|
| L5 large local model | Ollama (e.g. `llama3.1:70b` q4 or best fit) |
| MCP server (ingress) | Python — agents query daari |
| **MCP client (egress)** | Call local/corp MCP servers — [integrations.md](integrations.md) |
| **ProviderRegistry plugins** | `entry_points`, `.daari/providers/` |
| **Skills loader** | `.daari/skills/*.yaml` |
| Per-project profiles | YAML in `.daari.yaml` per repo |
| Optional stats UI | TypeScript + React — reads localhost API |

### Live source providers (Lt-fetch)

| Provider family | Ships | Language |
|-----------------|-------|----------|
| **Open-Meteo** | Weather | Python |
| **wttr.in** | Weather fallback | Python |
| **Generic REST** | Pluggable open APIs | Python |
| **Google Custom Search API** | Search, weather snippets, news | Python |
| **sources.yaml** | Priority + keys | YAML config |

Spec: [sources-integration.md](sources-integration.md) (subset of [IntegrationProvider](integrations.md))

### Clients

| Client | New capability |
|--------|----------------|
| MCP agents | Query routing decisions natively |
| All OpenAI-compat | Per-project tier maps |
| Corp MCP servers | daari calls tools on VPN/local network |

---

## Phase C2 — Client expansion + browser Google auth (v2b)

**Duration:** ~3–4 weeks  
**Language:** Python gateway + optional Kotlin (IntelliJ plugin)

| Component | Tech | Language |
|-----------|------|----------|
| **Browser extension** (Google auth) | Search via user session | **TypeScript** |
| **Anthropic-compat gateway** | Second HTTP router | Python |
| `daari setup claude-code` | Config patch | Python |
| Richer IntelliJ registry | More refactor intents | Python CLI → **Kotlin plugin** if CLI insufficient |
| `daari setup vscode` | Lt via code CLI | Python |
| MLX backend (Apple) | Optional L3–L5 executor | Python bindings |

### Clients fully supported

| Client | Integration | Phase C2 |
|--------|-------------|----------|
| **Claude Code** | Anthropic-compat base URL | ✅ |
| **Cursor** | OpenAI-compat (existing) | ✅ |
| **IntelliJ** | Lt + optional plugin | ✅ |
| **VS Code** | Lt via CLI | ✅ |
| **Future UI** | TS dashboard | Optional |

---

## Phase C3 — Enterprise integrations

**Duration:** ~2–3 weeks after C2  
**Goal:** Company-local APIs without LLM — Sourcegraph, GHE, GitLab, custom corp plugins

| Integration | Provider |
|-------------|----------|
| Sourcegraph | `daari-provider-sourcegraph` or builtin |
| GitHub Enterprise | REST provider |
| GitLab self-hosted | REST provider |
| Custom corp APIs | Generic HTTP provider + skills |

Spec: [integrations.md](integrations.md) · [ADR-0011](../adr/0011-pluggable-integration-providers.md)

Corp API integrations only — fleet/cache/learning in **Phase E**: [enterprise.md](enterprise.md).

---

## Phase E — Enterprise platform (later)

**Duration:** multi-sprint after C3  
**Goal:** Distributed install, org-wide cache, org collective learning  
**Prerequisite:** Phase B+ (L1, CCS); C3 optional

| Sub-phase | Ships |
|-----------|-------|
| **E1** | `enterprise.yaml`, install bundle, org policy sync, profiles |
| **E2** | L0-org / L1-org / CCS-org + self-hosted org cache service |
| **E3** | Org feedback loop, shared routing profile, tier tuning |

Spec: [enterprise.md](enterprise.md) · [ADR-0014](../adr/0014-enterprise-distributed-org-learning.md)

---

## Visual timeline

```mermaid
gantt
    title daari roadmap
    dateFormat YYYY-MM-DD
    section Phase A
    Tracer bullet MVP           :a1, 2026-06-16, 3w
    section Phase A1
    Install and L6              :a2, after a1, 1w
    section Phase B
    L1 L2 Lt CLI L4             :b1, after a2, 4w
    Lt IntelliJ                 :b2, after b1, 2w
    section Phase C
    MCP profiles L5             :c1, after b2, 4w
    Anthropic Claude Code       :c2, after c1, 4w
    section Phase E
    Enterprise E1 E2 E3         :e1, after c2, 8w
```

---

## Tech stack by phase (summary table)

| Phase | Python | Bash | TypeScript | Java/Kotlin |
|-------|--------|------|------------|-------------|
| A | ✅ Core | — | — | — |
| A.1 | ✅ + setup | ✅ install.sh | — | — |
| B | ✅ + Lt subprocess | — | — | — |
| C1 | ✅ + MCP | — | ⚠️ UI optional | — |
| C2 | ✅ + Anthropic gateway | **TS extension** | ⚠️ UI | ⚠️ IntelliJ plugin |
| D | ✅ + ML feedback loop | — | — | Local fine-tune libs |
| E | ✅ + org cache/learning clients | — | ⚠️ admin dashboard | — |

---

## Phase D — Local learning & collective improvement (future)

**Goal:** Each installation gets smarter locally; optional opt-in helps next release for everyone.

### D1 — Personal feedback loop (on-device)

| Component | Tech |
|-----------|------|
| Feedback capture | Python — user accepts/rejects response, tier override logs |
| Model picker | Python — recommend Ollama model per task type from local stats |
| Routing tuner | Python — adjust confidence thresholds from outcomes |

All data in `~/.daari/feedback/` — never leaves machine unless D3 opted in.

### D2 — Local fine-tuning (personal)

| Component | Tech |
|-----------|------|
| Fine-tune pipeline | Python + Ollama/MLX fine-tune tools |
| Training data | User corrections only — exported from local feedback store |
| Output | Personal adapter weights in `~/.daari/models/` |

**Not:** training a new foundation model. **Yes:** adapting a small local model to your workflow.

### D3 — Opt-in collective stats

| Component | Tech |
|-----------|------|
| Anonymized export | Python — tier success rates, latency percentiles, model IDs |
| Upload | Opt-in only; user reviews what leaves device |
| Content | **No** prompts/code by default |

### D4 — Better defaults next release

daari OSS project may publish improved routing defaults derived from aggregated opt-in stats (transparent, documented).

---

## Default models (recommended)

| Tier | Ollama model | Phase |
|------|--------------|-------|
| L3 SLM | `llama3.2:3b` | A |
| L4 medium | `llama3.1:8b` | B |
| Embeddings | `nomic-embed-text` | B |
| L5 large | `llama3.1:70b` (quantized) or best AS Mac fit | C1 |
| L6 frontier | User's OpenAI/Anthropic model | A.1 |

---

## Related docs

- [PRD v0.4](PRD.md)
- [routing-spec](routing-spec.md)
- [setup-spec](setup-spec.md)
- [Competitive landscape](../discovery/04-competitive-landscape.md)

# ADR-0013: Single-repo monorepo structure

Date: 2026-06-15  
Status: **accepted**

## Context

daari will use multiple languages over time:

| Language | Component | Phase |
|----------|-----------|-------|
| **Python 3.12** | Core daemon, router, cache, CLI, MCP server | A → B |
| **Bash** | `install.sh` | A.1 |
| **TypeScript** | Browser extension (Google auth), optional stats UI | C1–C2 |
| **Kotlin/Java** | Optional IntelliJ plugin if CLI insufficient | C2+ |

Question: **one repo (`daari`) or multiple repos?**

## Decision

**Single repo — monorepo.** All daari-owned code lives in `naveenreddyalka/daari`.

### Rules

1. **One Python brain** — routing, cache, providers, policy never duplicated in other languages ([ADR-0005](0005-python-tech-stack.md)).
2. **Other languages = surfaces only** — UI, browser extension, IDE plugin talk to localhost Python API; no routing logic.
3. **`packages/`** for non-Python artifacts — clear boundary, independent build/test.
4. **Separate repo only when reusable outside daari** — e.g. `agent-skills` (cross-project skills), not daari core.

### Target layout

```
daari/                              # repo root
├── daari/                          # Python package — THE brain (pip install -e .)
│   ├── gateway/                    # runtime wire adapters (openai, anthropic, mcp)
│   ├── clients/                    # per-tool setup recipes (cursor, claude_code, …)
│   ├── cli/ router/ cache/ …
│   └── tools/backends/             # Lt runtime (intellij, git) — Phase B+
├── packages/                       # Non-Python — added when phase ships
│   ├── browser-extension/          # Phase C2 — TypeScript (Chrome/Firefox)
│   ├── web-ui/                     # Phase C1 optional — TypeScript/React dashboard
│   └── intellij-plugin/            # Phase C2+ optional — Kotlin if CLI insufficient
├── evals/
│   └── routing/
├── docs/
│   ├── adr/
│   ├── prd/
│   ├── plans/
│   └── setup/
├── scripts/
│   └── install.sh                  # Phase A.1
├── pyproject.toml                  # Python project root
├── package.json                    # Phase C1+ — npm/pnpm workspace root for packages/*
├── .github/workflows/              # CI: Python always; TS/Kotlin when packages exist
├── CONTEXT.md
└── README.md
```

**Phase A (now):** Only `daari/` Python tree + `docs/` + `evals/`. `packages/` may be absent or contain `README.md` placeholder.

### Where client-specific code lives

Client-specific work splits into **three layers** — do not mix them:

| Layer | What | Path | Examples |
|-------|------|------|----------|
| **1. Gateway (runtime wire format)** | How HTTP/API requests arrive at daari | `daari/gateway/` | `openai.py` ← Cursor, OpenAI SDK · `anthropic.py` ← Claude Code |
| **2. Client recipes (setup)** | Detect, patch, undo **external app config** | `daari/clients/<name>/` | Cursor settings JSON · Claude Code env · IntelliJ path for Lt |
| **3. Human docs (manual fallback)** | Copy-paste setup when automation not ready | `docs/setup/<name>.md` | [cursor.md](../setup/cursor.md) |

**Cursor and Claude Code are not packages in `packages/`.** They are third-party apps on the user's machine. daari ships **recipes** that configure them to point at `localhost:11435`.

```
daari/                                    # Python package
├── gateway/                              # RUNTIME — protocol adapters
│   ├── base.py                           # GatewayAdapter protocol
│   ├── internal.py                       # InternalRequest / InternalResponse
│   ├── openai.py                         # Cursor, OpenAI SDK, curl
│   ├── anthropic.py                      # Claude Code (Phase C2)
│   └── mcp.py                            # MCP agents (Phase C1)
│
├── clients/                              # SETUP — per-tool install/configure
│   ├── base.py                           # ClientRecipe protocol
│   ├── registry.py                       # detect + dispatch for `daari setup`
│   ├── wizard.py                         # interactive `daari setup` (Phase A.1)
│   │
│   ├── cursor/                           # AI client
│   │   ├── recipe.py                     # apply / undo / dry-run
│   │   ├── detect.py                     # is Cursor installed?
│   │   └── paths.py                      # macOS settings file locations
│   │
│   ├── claude_code/                      # AI client (Phase C2)
│   │   └── recipe.py
│   │
│   ├── openai_compat/                    # Generic SDK — print env vars
│   │   └── recipe.py
│   │
│   ├── intellij/                         # Lt backend (NOT AI client)
│   │   └── recipe.py                     # register `idea` CLI path
│   │
│   └── vscode/                           # Lt backend (Phase C2+)
│       └── recipe.py
│
├── cli/
│   ├── setup.py                          # `daari setup` → clients/registry
│   └── doctor.py                         # health checks per client
│
└── tools/                                # RUNTIME Lt executors (Phase B+)
    └── backends/
        ├── intellij.py                   # subprocess → idea CLI
        └── git.py
```

### Two kinds of “client”

| Kind | Role | Setup lives in | Gateway |
|------|------|----------------|---------|
| **AI client** | Sends chat to daari | `clients/cursor/`, `clients/claude_code/` | openai or anthropic |
| **Lt backend** | IDE/CLI daari invokes | `clients/intellij/` + `tools/backends/intellij.py` | none — not an AI client |

Wizard copy must explain: *“IntelliJ = tools daari runs for you; Cursor = AI chat pointed at daari.”*

### `packages/` vs `clients/`

| Directory | Contains |
|-----------|----------|
| **`daari/clients/`** | Python code to **configure external apps** (Cursor, Claude Code, IntelliJ) |
| **`packages/`** | **Code we ship** that runs separately (browser extension, web UI, optional IDE plugin JAR) |

Browser extension is daari-owned TypeScript → `packages/browser-extension/`.  
Cursor is not in the repo — only the recipe that patches its settings.

### Docs mirror

```
docs/setup/
├── cursor.md           # manual Phase A fallback
├── claude-code.md      # Phase C2
├── openai-compat.md
└── intellij.md         # Lt backend
```

Automation recipe in `daari/clients/`; human doc in `docs/setup/` — keep in sync.

### Package boundaries

```
┌─────────────────────────────────────────────────────────┐
│  packages/browser-extension  (TS)                       │
│  packages/web-ui             (TS)                       │
│  packages/intellij-plugin    (Kotlin)                   │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / localhost only
                           ▼
┌─────────────────────────────────────────────────────────┐
│  daari/ (Python) — daemon, router, cache, CLI           │
│  Bound: 127.0.0.1:11435 (ADR-0006)                      │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
                    Ollama, git, IDE CLI, …
```

### Build & install

| Artifact | How users get it |
|----------|------------------|
| **Core** | `pip install -e .` or `./install.sh` → `daari` CLI |
| **Browser ext** | Load unpacked from `packages/browser-extension/dist` or store publish later |
| **Web UI** | Optional `pnpm --filter web-ui dev` — not required for core |
| **IntelliJ plugin** | Optional — most users use Python Lt + `idea` CLI first |

### CI strategy

| Phase | CI jobs |
|-------|---------|
| A–B | Python: ruff, pytest, routing eval |
| C1+ | + `packages/web-ui` lint/build if present |
| C2+ | + browser-extension build |

No Kotlin CI until plugin package exists.

### What stays OUT of this repo

| Repo | Why separate |
|------|--------------|
| **`agent-skills`** | Reusable across daari, Cursor, other agents — not daari runtime |
| **Company corp configs** | `.daari/integrations.yaml`, internal MCP — user/enterprise git |
| **Provider plugins (optional future)** | `daari-provider-sourcegraph` on PyPI — only if package size/licensing warrants split |

Default: enterprise providers can live in `daari/providers/plugins/` or `.daari/providers/` drop-in — still single repo for builtins.

## Consequences

**Positive**
- One clone, one issue tracker, one release cadence for OSS
- Matches solo/small-team velocity
- Clear rule: Python owns routing; TS/Kotlin are thin clients

**Negative**
- Repo grows with TS/Kotlin toolchains — mitigated by `packages/` isolation
- IntelliJ plugin build is heavy — optional package, Phase C2+ only

## Related

- [ADR-0005](0005-python-tech-stack.md) — Python core
- [ADR-0010](0010-browser-bridge-google-search.md) — browser extension in TS
- [ROADMAP.md](../prd/ROADMAP.md) — language per phase
- [phase-a.md](../plans/phase-a.md) — initial Python layout

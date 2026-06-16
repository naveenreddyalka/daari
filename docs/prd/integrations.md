# Integrations — Provider framework & enterprise plugins

> **Status:** Draft  
> **Related:** [ADR-0011](../adr/0011-pluggable-integration-providers.md) · [sources-integration.md](sources-integration.md) · [ROADMAP.md](ROADMAP.md)

---

## Principle

**Ground-level support now, integrations later.**

Phase A–B builds the **provider registry** and protocol. Individual integrations (MCP, Sourcegraph, GHE, skills) ship as **plugins** in Phase C+ — no router rewrites.

---

## What “integration” means in daari

Anything that **does work without an LLM** via a registered backend:

| Type | Examples | Config |
|------|----------|--------|
| **Open APIs** | Open-Meteo, wttr | `sources.yaml` |
| **Google** | CSE API, browser extension | `sources.yaml` |
| **Local MCP** | Corp MCP server on laptop/VPN | `integrations.yaml` |
| **Enterprise APIs** | Sourcegraph, GitHub Enterprise, GitLab | `integrations.yaml` |
| **Local git** | Self-hosted git, custom remotes | `integrations.yaml` + shell |
| **Skills** | Packaged rules + provider actions | `.daari/skills/` |

All implement the same **`IntegrationProvider`** interface ([ADR-0011](../adr/0011-pluggable-integration-providers.md)).

---

## Architecture

```
                    ┌─────────────────────────────────┐
                    │         daari router            │
                    └───────────────┬─────────────────┘
                                    │
                    ┌───────────────▼─────────────────┐
                    │      ProviderRegistry           │
                    │  (ground level — Phase A)       │
                    └───────────────┬─────────────────┘
          ┌──────────┼──────────┬──────────┬──────────┼──────────┐
          ▼          ▼          ▼          ▼          ▼          ▼
       cache      ollama     shell    open_meteo   mcp:*    sourcegraph
       (A)         (A)        (B)       (C1)      (C1+)      (C2+)
```

---

## Config — `~/.daari/integrations.yaml`

```yaml
integrations:
  enabled: true

  mcp_servers:
    - id: local-tools
      transport: stdio
      command: ["daari-mcp-local", "serve"]
      capabilities: [filesystem, git]

    - id: corp-sourcegraph
      transport: sse
      url: http://mcp.internal.corp:8080
      env:
        SOURCEGRAPH_TOKEN: ${SOURCEGRAPH_TOKEN}
      capabilities: [code_search, symbol_lookup]

  enterprise:
    sourcegraph:
      url: https://sourcegraph.company.com
      token: ${SOURCEGRAPH_TOKEN}

    github_enterprise:
      url: https://github.company.com/api/v3
      token: ${GHE_TOKEN}

    gitlab:
      url: https://gitlab.company.com
      token: ${GITLAB_TOKEN}

  allowed_providers:          # enterprise lockdown
    - cache
    - ollama
    - shell
    - mcp:local-tools
    - mcp:corp-sourcegraph
    - sourcegraph
```

Project override: `.daari/integrations.yaml` in repo root.

---

## Example flows

### Sourcegraph (Phase C2)

```
"Find all references to PaymentService in our monorepo"
  → integration rule match
  → provider: sourcegraph
  → API call (local/corp network)
  → CCS cache
  → formatted result — no LLM
```

### Local MCP (Phase C1+)

```
"List open PRs for this repo"
  → provider: mcp:corp-git
  → MCP tool `list_pull_requests`
  → response
```

### Skill pack (Phase C1+)

```
# .daari/skills/sourcegraph.yaml
skill: sg-search
trigger: "(?i)find (usages|references) of"
provider: sourcegraph
action: search
```

---

## Phase plan

| Phase | Ground level | Integrations shipped |
|-------|--------------|----------------------|
| **A** | `ProviderRegistry` + protocol; cache + ollama providers | — |
| **B** | shell provider; health checks in `daari doctor` | — |
| **C1** | MCP client transport; plugin entry_points; skills loader | Open-Meteo, Google CSE, **generic MCP** |
| **C2** | Enterprise config validation; audit logging | **Sourcegraph**, GHE, GitLab, browser ext |
| **C3** | Provider marketplace / `daari-provider-*` packages | Jira, Confluence, custom corp plugins |
| **D** | Feedback loop per provider (success rates) | Auto-tune provider priority |
| **E1–E3** | Enterprise platform | Distributed install, org cache, org learning — [enterprise.md](enterprise.md) |

---

## Plugin packaging

| Method | Use case |
|--------|----------|
| **Builtin** | cache, ollama, shell — in `daari/providers/builtin/` |
| **Config-only** | REST APIs via generic `http_provider` template |
| **Python entry point** | `pip install daari-provider-sourcegraph` |
| **Drop-in file** | `.daari/providers/my_corp_api.py` |
| **Skills repo** | Separate `agent-skills` / company git — YAML + optional Python |

---

## Relationship to other ADRs

| ADR | Role |
|-----|------|
| 0007 | Ingress: OpenAI/Anthropic/MCP **adapters** (clients → daari) |
| 0011 | Egress: **providers** (daari → backends) |
| 0009/0010 | Subset of providers: open API + Google |
| 0008 | L2-dev + CCS for dev commands |

Ingress adapters = how tools **talk to** daari.  
Integration providers = how daari **talks to** the world.

---

## Skills repo strategy

| Location | Content |
|----------|---------|
| `naveenreddyalka/daari` | Core registry + builtin providers |
| `naveenreddyalka/agent-skills` *(planned)* | Reusable cross-project skills |
| Company internal git | Corp integrations + MCP configs (not in public daari repo) |

Skills = triggers + provider binding — not duplicate routing logic.

# ADR-0011: Pluggable integration provider framework

Date: 2026-06-15  
Status: **accepted**

## Context

daari must support **company-local integrations** in later phases:

- Local MCP servers (tools running on corp network)
- Internal REST APIs (Sourcegraph, internal git, Jira, artifact repos)
- Local skills / agent capabilities
- Enterprise git (GitHub Enterprise, GitLab self-hosted)

These cannot be hard-coded per vendor. The **ground-level architecture** (Phase A–B) must expose a **provider registry** so integrations ship as plugins in Phase C+ without rewriting the router.

## Decision

Introduce a unified **Integration Provider** abstraction at the foundation of daari. All backends — Ollama, open APIs, Google, MCP, Sourcegraph — register through the same interface.

### Core abstraction

```
InternalRequest
      │
      ▼
   Router (picks tier + provider id)
      │
      ▼
ProviderRegistry.get(provider_id).execute(context)
      │
      ▼
InternalResponse
```

```python
# Conceptual — daari/providers/base.py
class IntegrationProvider(Protocol):
    id: str                    # e.g. "open_meteo", "sourcegraph", "mcp:local-tools"
    tier: Tier                 # L0 | Lt | L2-live | L3 | integration
    capabilities: set[str]     # "weather", "code_search", "git", "mcp_tool"

    async def can_handle(self, ctx: RequestContext) -> float  # 0.0–1.0 confidence
    async def execute(self, ctx: RequestContext) -> ProviderResult
    async def health(self) -> HealthStatus
```

### Provider categories

| Category | Examples | Tier | Phase (impl) |
|----------|----------|------|--------------|
| **cache** | L0, L1, CCS | L0 | A |
| **model** | Ollama, MLX, frontier | L3–L6 | A+ |
| **shell** | git, npm, lint | Lt | B |
| **fetch_open** | Open-Meteo, wttr | L2-live | C1 |
| **fetch_google** | Google CSE, browser ext | L2-live | C1–C2 |
| **mcp** | Local/corp MCP servers | Lt / integration | C1+ |
| **enterprise_api** | Sourcegraph, GHE, GitLab, Jira | integration | C2+ |
| **skill** | `.daari/skills/`, packaged recipes | L2 / Lt | C1+ |

**`integration` tier label:** Same routing slot as Lt/L2-live — executes via registered provider, **no LLM**.

### MCP as first-class provider type

Local or company MCP servers register in `integrations.yaml`:

```yaml
mcp_servers:
  - id: corp-tools
    transport: stdio          # or sse, http
    command: ["npx", "-y", "@company/mcp-server"]
    env:
      SOURCEGRAPH_TOKEN: ${SOURCEGRAPH_TOKEN}
    capabilities: [code_search, symbol_lookup]

  - id: local-git-mcp
    transport: sse
    url: http://localhost:3001/mcp
    capabilities: [git, pr_status]
```

Router flow:
```
"Find all usages of AuthService"
  → L2-dev / integration rule match
  → ProviderRegistry → mcp:corp-tools
  → MCP tool call → Sourcegraph backend
  → CCS cache → response (no L3/L6)
```

daari acts as **MCP client** (or hosts MCP gateway per [ADR-0007](0007-pluggable-gateway-adapters.md) — MCP adapter on ingress, MCP client on egress).

### Enterprise API providers

Built as provider plugins — not core code forks:

```yaml
enterprise:
  sourcegraph:
    enabled: true
    url: https://sourcegraph.company.com
    token: ${SOURCEGRAPH_TOKEN}
    capabilities: [code_search, blame, defs]

  github_enterprise:
    enabled: true
    url: https://github.company.com/api/v3
    token: ${GHE_TOKEN}
    capabilities: [pr, issues, repo_search]

  gitlab:
    url: https://gitlab.company.com
    token: ${GITLAB_TOKEN}
```

Module layout:
```
daari/providers/
  base.py              # IntegrationProvider protocol — Phase A (empty registry)
  registry.py          # ProviderRegistry — Phase A
  builtin/             # shipped providers
    ollama.py          # Phase A
    cache.py           # Phase A
    shell.py           # Phase B
    open_meteo.py      # Phase C1
    google_cse.py      # Phase C1
  plugins/             # optional entry_points / .daari/providers/
    sourcegraph.py     # Phase C2
    mcp_client.py        # Phase C1
```

Third-party / company plugins: `pip install daari-provider-sourcegraph` or drop file in `.daari/providers/`.

### Skills integration

**Skills** = packaged provider + rules (aligns with user's separate `agent-skills` repo):

```yaml
# .daari/skills/sourcegraph-search.yaml
skill: sourcegraph-search
triggers:
  - "(?i)find (all )?(usages|references) of"
provider: sourcegraph
action: search_symbols
```

Skills load at daemon start → register triggers with L2-dev / integration rules → dispatch to provider.

### Ground-level vs later phases

| Ground level (Phase A–B) | Built later (Phase C+) |
|--------------------------|-------------------------|
| `IntegrationProvider` protocol | Sourcegraph provider |
| `ProviderRegistry` | GitHub Enterprise provider |
| `integrations.yaml` schema | MCP client transport |
| Provider health in `daari doctor` | Company-specific MCP servers |
| `daari_meta.provider_id` in responses | Skill packs from `agent-skills` repo |
| Plugin discovery (entry points) | Jira, Confluence, internal wiki |

**Phase A tracer bullet** ships registry + 2 builtin providers (cache, ollama). Registry is **empty of enterprise** until C1+.

### Routing update

```
L0 → CCS → L1 → L2-dev → L2-live → L2 → integration providers → Lt → L3 … L6
                                              ↑
                                    MCP, Sourcegraph, skills
```

`integration providers` evaluated when request matches enterprise/skill rules or MCP-exposed capabilities.

### Security (enterprise)

| Rule | Detail |
|------|--------|
| Tokens | Env or secret store — never in git |
| MCP | User/admin registers allowed servers |
| Network | Corp providers may require VPN — user responsibility |
| Audit | Log `provider_id` + action; no prompt leak |
| Allowlist | `integrations.allowed_providers` in enterprise config |

## Consequences

**Positive**
- One extension model for weather, Google, Sourcegraph, MCP
- Company IT can ship internal providers without forking daari
- Skills repo plugs in cleanly

**Negative**
- Registry abstraction adds upfront design cost in Phase A
- MCP + enterprise = many edge cases per vendor

## Related

- [sources-integration.md](../prd/sources-integration.md) — open API + Google subset
- [ADR-0007](0007-pluggable-gateway-adapters.md) — ingress adapters
- [ADR-0009](0009-live-factual-fetch-l2-live.md), [ADR-0010](0010-browser-bridge-google-search.md)
- PRD user stories #69–72

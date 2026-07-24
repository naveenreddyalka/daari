# Enterprise — distributed install, org cache, collective learning

> **Status:** E1 config/runtime scaffold + E2/E3 MVP tracer bullets shipped. Full E1 fleet bootstrap (MDM bundles, signed policy push) is **not** built — it moved to [ROADMAP-v2 Train F4](ROADMAP-v2.md) along with Redis/Postgres backends, stateless replicas, Helm, SSO/RBAC.  
> **Related:** [ADR-0014](../adr/0014-enterprise-distributed-org-learning.md) · [integrations.md](integrations.md) · [PRD](PRD.md)

---

## Scope

Enterprise features ship **after** individual/local OSS maturity (Phase A–D) and corp API integrations (Phase C3). They are **opt-in** — OSS daari works with zero enterprise services.

| Phase | Focus |
|-------|-------|
| **C3** | Company-local **APIs** (Sourcegraph, GHE, GitLab) — per [integrations.md](integrations.md) |
| **E1** | **Distributed install** — many machines, one org policy |
| **E2** | **Org-wide shared cache** — L0/L1/CCS across company sessions |
| **E3** | **Org collective learning** — feedback from all enterprise users improves routing for the tenant |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Org control plane (self-hosted on corp network — Phase E)    │
│  · policy sync    · org cache service    · learning aggregate │
└────────────────────────────┬─────────────────────────────────┘
                             │ org token / mTLS
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   daari (dev laptop)   daari (dev laptop)   daari (CI runner)
   local L0/L1/CCS      local tiers           headless profile
         │                   │                   │
         └───────────────────┴───────────────────┘
              optional: org cache + org routing profile
```

Each machine **still runs a local daemon** ([ADR-0006](../adr/0006-local-daemon-security.md)). Enterprise adds optional upstream services on the **company network** — not cloud inference for every request.

---

## E1 — Distributed installation

| Capability | Detail |
|------------|--------|
| **Install bundle** | Version-pinned daari + `enterprise.yaml` — MDM, Ansible, internal package mirror, `daari enterprise bootstrap` |
| **Org identity** | `tenant_id`, control-plane URL, org token in `~/.daari/enterprise.yaml` |
| **Central policy** | Allowlists, frontier disable, tier caps, `integrations.allowed_providers` — pushed or pulled |
| **Profiles** | `developer`, `ci`, `admin` — different Lt, cache, L6 rules |
| **Fleet health** | Optional: version + `daari doctor` summary to org dashboard — **no prompt content** |

Local routing stays on-device; control plane is **config + shared services**, not a proxy for all LLM calls.

---

## E2 — Org-wide shared cache

Routing consults **org scope** after local miss, before model:

```
L0 (local) → L0-org → L1 (local) → L1-org → CCS (local) → CCS-org → … → L3+
```

| Store | Shared across company | Never shared |
|-------|----------------------|--------------|
| **L0-org** | Exact prompt hash (sanitized key) | Secrets, user-specific env |
| **L1-org** | Semantic matches on **admin-approved** prompt classes | Raw paths with PII, credentials |
| **CCS-org** | Command **patterns** + redacted stdout summaries | Full stderr with tokens, sensitive commands |

**Governance:**

- Admin: `enterprise.cache.enabled`, `share_classes` (e.g. `lint_output`, `doc_qa`, `internal_api_fetch`)
- Redaction required before any org upload
- Opt-out: `X-Daari-No-Org-Cache`, project `.daariignore`
- Admin-controlled TTL and revocation

**Effect:** When one engineer asks a common internal question or runs an allowlisted command, others in the **same tenant** hit org cache — higher $0 tier rate for the whole company.

**Implementation status (v1.0.1-dev):**

- `daari org-cache serve` runs a lightweight FastAPI cache API (`/v1/org-cache/get`, `/put`, `/stats`)
- Router now checks `L0-org` and `L1-org` via `org.shared_cache_url` after local misses
- Router write-through uploads local model responses to org cache (`L0` + key-based `L1`)
- Bearer auth supported via `DAARI_ORG_CACHE_TOKEN`; token enforcement is configurable (`shared_cache_require_token`)
- Storage defaults to `~/.daari/org/<org_id>/shared-cache/`

---

## E3 — Org collective learning

| Scope | Who benefits | Data |
|-------|--------------|------|
| **D1 Personal** (Phase D) | One machine | Local only |
| **D3 OSS collective** (Phase D) | Global daari users (opt-in) | Anonymized public stats |
| **E3 Org learning** | **All users in same company** | Org-admin-governed |

**Default signals (metadata only):**

- Tier chosen vs user override
- Cache hit/miss by task class
- Lt success/failure (exit class, not full output)
- Explicit thumbs up/down (if client supports)

**Uses:**

- Auto-tune tier thresholds per org
- Promote L2-dev rules and skills that work company-wide
- Recommend local models per task type for org hardware
- Push shared **org routing profile** to all agents

**Not default:** uploading prompts, code, or full CCS stdout — requires explicit org policy + user notice.

**Implementation status (v1.0.1-dev):**

- `daari org-cache serve` now also exposes org learning API endpoints:
  - `POST /v1/org-learning/feedback`
  - `GET /v1/org-learning/profile`
  - `PUT /v1/org-learning/profile` (admin token required)
- Feedback is metadata-only (`tier`, `cache_hit`, `latency_ms`, optional `rating`, optional `task_class`)
- Learning store persists under `~/.daari/org/<org_id>/learning/feedback.sqlite3`
- Router now submits fire-and-forget feedback after each response when org learning is enabled
- Startup profile sync merges org routing preferences into local `routing.prefer` and `routing.confidence_threshold`
- CLI includes:
  - `daari org-learning stats`
  - `daari org-learning export`

---

## Config sketch (`~/.daari/enterprise.yaml`)

```yaml
enterprise:
  enabled: true
  tenant_id: acme-corp
  control_plane_url: https://daari.internal.acme.com
  org_token: ${DAARI_ORG_TOKEN}

  cache:
    enabled: true
    share_classes: [lint_output, doc_qa, internal_api_fetch]
    no_org_cache_default: false   # admin can force; user override via header

  learning:
    enabled: true
    upload_prompts: false         # explicit opt-in only
    upload_code: false

  profile: developer              # developer | ci | admin
```

---

## Relationship to Phase C3

| C3 | E |
|----|---|
| Sourcegraph, GHE, GitLab **providers** | **How** daari is deployed and improved **across** the org |
| `integrations.yaml` per user/project | `enterprise.yaml` + control plane |
| Single-machine integrations | Fleet + shared cache + learning |

C3 can ship without E. E assumes C3 integrations may already be in org policy.

---

## Out of scope for E (unless reopened)

- Hosted SaaS control plane as default (self-hosted first)
- Cross-tenant cache or learning
- Mandatory prompt/code upload
- Replacing corp SSO or MDM — integrate with them

---

## User stories

See PRD #78–#83.

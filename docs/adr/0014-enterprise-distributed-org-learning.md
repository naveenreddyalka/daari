# ADR-0014: Enterprise — distributed install, org cache, collective learning

Date: 2026-06-15  
Status: **accepted**

## Context

Individual daari installs optimize **per machine** (local L0, CCS, personal learning in Phase D). Enterprises need:

1. **Distributed installation** — daari on many developer machines with consistent config, policy, and updates
2. **Org-wide shared cache** — when one engineer's prompt/command result is safe to reuse, others in the **same company** benefit without re-running models or tools
3. **Collective learning from company feedback** — routing corrections and tier success signals aggregate at **tenant** level so the org's daari deployment improves for everyone over time

This must not break OSS local-first defaults: enterprise features are **opt-in deployment mode**, admin-controlled, and separate from mandatory telemetry.

## Decision

Introduce an **Enterprise deployment profile** with three cooperating layers:

```
┌──────────────────────────────────────────────────────────────┐
│  Org control plane (self-hosted or managed — Phase E)         │
│  policy · shared cache · learning aggregate · install bundle  │
└────────────────────────────┬─────────────────────────────────┘
                             │ mTLS / org token
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   daari (laptop)      daari (laptop)      daari (CI runner)
   local L0/L1/CCS     local tiers         headless profile
         │                   │                   │
         └───────────────────┴───────────────────┘
                    org cache + org routing profile
```

Each machine **still runs a local daemon** ([ADR-0006](0006-local-daemon-security.md)). Enterprise adds **optional upstream services** on the company network — not a return to "everything in the cloud."

### 1. Distributed installation

| Component | Role |
|-----------|------|
| **Install bundle** | Version-pinned package + `enterprise.yaml` — MDM, Ansible, internal brew, or `daari enterprise bootstrap` |
| **Org identity** | `tenant_id`, org token, control-plane URL in `~/.daari/enterprise.yaml` |
| **Central policy** | Allowlists, `integrations.allowed_providers`, tier caps, frontier disable — pulled or pushed |
| **Profiles** | `developer`, `ci`, `admin` — different Lt/cache/L6 rules |
| **Health reporting** | Optional: daari version + doctor summary to org dashboard (no prompt content) |

Local routing remains on-device; control plane is **config + shared services**, not a proxy for every inference call.

### 2. Org-wide shared cache

Extend cache tiers with **org scope** — consulted after local miss, before model:

```
L0 (local) → L0-org → L1 (local) → L1-org → CCS (local) → CCS-org → … → L3+
```

| Store | What is shared | What is NOT shared |
|-------|----------------|-------------------|
| **L0-org** | Exact prompt hash matches (org-sanitized key) | User-specific secrets, `.env` content |
| **L1-org** | Semantic similarity on **approved** prompt classes | Raw repo paths with PII, credentials |
| **CCS-org** | Command **patterns** + redacted stdout summaries | Full stderr with tokens, sensitive commands |

**Rules:**

- Admin configures `enterprise.cache.enabled` and `share_classes` (e.g. `lint_output`, `doc_qa`, `internal_api_fetch`)
- Entries require **redaction pass** before upload; blocklist never syncs
- User/project can opt out: `X-Daari-No-Org-Cache`, `.daariignore` patterns
- TTL and revocation controlled by org admin

Implementation: org cache service (Redis/S3-compatible/self-hosted daari-cache) — **Phase E2**. Protocol in [enterprise.md](../prd/enterprise.md).

### 3. Org collective learning

Distinct from Phase D personal learning and D3 global OSS opt-in:

| Scope | Who benefits | Data |
|-------|--------------|------|
| **D1 Personal** | One machine | Local only |
| **D3 OSS collective** | All daari users (opt-in) | Anonymized global stats |
| **E3 Org learning** | **All users in same tenant** | Org-admin-governed feedback |

**Signals (default — metadata only):**

- Tier chosen vs user override
- Cache hit/miss rates per task class
- Lt success/failure (exit code class, not full output)
- Explicit thumbs up/down on response (if client supports)

**Uses:**

- Auto-tune tier thresholds per org
- Promote L2-dev rules and skills that work for the company
- Recommend local model per task type on org hardware profile
- Optional org-specific routing profile pushed to all agents

**Not default:** uploading prompts, code, or CCS full stdout — requires explicit org policy + user notice.

### 4. Module placement

| Piece | Location | Phase |
|-------|----------|-------|
| Enterprise config schema | `daari/config/enterprise.py` | E1 |
| Org cache client | `daari/cache/org.py` | E2 |
| Learning feedback client | `daari/learning/org.py` | E3 |
| Control plane | Separate deployable (`daari-enterprise/` or managed) | E1+ |

OSS core stays functional with **zero** enterprise services configured.

## Security & compliance

| Requirement | Approach |
|-------------|----------|
| Tenant isolation | Strict `tenant_id`; no cross-org cache or learning |
| Data residency | Self-hosted control plane on corp network |
| Audit | Admin log: policy changes, cache class toggles, learning opt-in |
| SSO / identity | Integrate with corp IdP for org token (Phase E1+) |
| Minimum privilege | CI profile: no destructive Lt, no org cache write |

## Phase

| Phase | Ships |
|-------|-------|
| **E1** | Distributed install bundle, org policy sync, enterprise.yaml |
| **E2** | L0-org, L1-org, CCS-org client + cache service |
| **E3** | Org feedback aggregation, shared routing profile, tier tuning |

Enterprise API integrations (Sourcegraph, etc.) remain **Phase C3** — E builds on top.

## Consequences

**Positive**
- Network effect inside company — more users → higher $0 tier rate for everyone
- IT can standardize daari like any dev tool
- Aligns with "train from company feedback" without mandatory prompt exfiltration

**Negative**
- Control plane is significant build; likely self-hosted first
- Cache sharing needs careful redaction — misconfiguration risk
- Not all orgs will self-host; managed offering is future product decision

## Related

- [enterprise.md](../prd/enterprise.md) — full spec
- [ADR-0008](0008-developer-command-rules-and-context-cache.md) — CCS
- [ADR-0012](0012-execution-policy.md) — policy before Lt
- PRD user stories #78–#83
- Phase D — personal / global OSS learning (orthogonal)

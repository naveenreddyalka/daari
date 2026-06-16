# ADR-0012: Execution policy (Lt) and CCS cache policy

Date: 2026-06-15  
Status: **accepted**

## Context

**Lt** runs shell, IDE, and integration backends — the highest-risk path in daari. **CCS** stores prior command/fetch output for reuse. These need distinct policy models:

| Layer | Risk | Policy type |
|-------|------|-------------|
| **Lt** | Executes code on the machine | Allow / ask / deny before run |
| **CCS** | Reads stored artifacts | Cache eligibility, TTL, redaction — no execution gate |

Scattered rules exist in [ADR-0008](0008-developer-command-rules-and-context-cache.md) and [routing-spec](../prd/routing-spec.md). This ADR unifies them under **PolicyEngine** (Lt) and **CCS policy** (cache sub-store).

## Decision

### 1. PolicyEngine — Lt execution (deny → ask → allow)

Every Lt dispatch passes through `PolicyEngine.evaluate()` before subprocess/IDE/API call:

```
L2-dev match → PolicyEngine.evaluate(command, context)
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
      DENY         ASK        ALLOW
   (blocklist)  (destructive/  (allowlist
    unknown)     unlisted)      match)
        │           │           │
        ▼           ▼           ▼
     reject    confirm prompt   Lt.execute()
                                    │
                                    ▼
                              CCS.write() (if eligible)
```

#### Outcomes

| Outcome | When | Behavior |
|---------|------|----------|
| **DENY** | Blocklist match, unknown command (no allowlist), frontier disabled for network fetch | HTTP 403-style error in chat response; log `policy:deny` |
| **ASK** | Destructive pattern, unlisted command with `tools.unknown: ask` | Return confirmation prompt; client resends with `X-Daari-Confirm-Tool: true` |
| **ALLOW** | Builtin allowlist, project allowlist, prior confirm in same request | Execute immediately |

#### Config merge order (most specific wins)

```
1. Blocklist (global — always applied)
2. Global allowlist     (~/.daari/config.yaml → tools.allow)
3. User overrides
4. Project allowlist    (.daari/commands.yaml)
5. Per-request headers  (X-Daari-Confirm-Tool, X-Daari-No-Cache)
```

#### Default posture by phase

| Phase | Unknown shell command | Destructive IDE op |
|-------|----------------------|-------------------|
| **B.0** | **DENY** (only LT-01–LT-04 patterns) | N/A (no IntelliJ) |
| **B.1** | **ASK** if `tools.unknown: ask`, else DENY | **ASK** always |
| **C1** | Enterprise profile may widen allowlist | Same + audit log |

```yaml
# ~/.daari/config.yaml
tools:
  auto_confirm: false          # default — destructive requires confirm
  unknown: deny                # deny | ask — unlisted commands
  allow:
    - pattern: "git status"
    - pattern: "git diff"
    - pattern: "eslint *"
  block:
    - pattern: "rm -rf *"
    - pattern: "curl * | sh"
    - pattern: "* > /dev/*"
```

```yaml
# .daari/commands.yaml (project)
commands:
  - id: team-lint
    match: "(?i)run team lint"
    exec: "./scripts/lint.sh"
    allow: true
    destructive: false
    ccs_ttl_seconds: 300
```

#### Confirmation response shape

When ASK, daari returns a normal chat completion with `daari_meta`:

```json
{
  "daari_meta": {
    "tier": "Lt",
    "policy": "ask",
    "pending_command": "idea refactor rename ...",
    "confirm_header": "X-Daari-Confirm-Tool"
  }
}
```

Client (Cursor agent) resends original request + header to proceed.

**Non-goals for MVP:** persistent session grants ("remember for 1 hour"), GUI confirm dialog — config + header only.

### 2. CCS cache policy (not execution)

CCS never executes. Policy governs **what gets stored and served**:

| Rule | Detail |
|------|--------|
| **Write after Lt/fetch** | Always attempt CCS write on successful Lt or Lt-fetch (unless excluded) |
| **TTL** | Per command class — e.g. `git status` 60s, `npm test` 3600s, weather 1800s |
| **Sensitive skip** | No CCS if command tagged `sensitive: true`, `X-Daari-No-Cache`, or matches redaction pattern |
| **Readonly query** | L2-dev DEV-* readonly patterns read CCS without re-run if fresh |
| **Invalidate** | `re-run` / `run again` patterns (DEV-07) bypass CCS; `daari context clear` |
| **Redaction** | Strip env vars, tokens from stdout before persist — `.daariignore` patterns |
| **Size limits** | Truncate stdout; full log on disk with rotation |

CCS does **not** use deny/ask/allow — if output exists and TTL valid, serve it.

### 3. Module placement

| Piece | Module | Phase |
|-------|--------|-------|
| PolicyEngine | `daari/policy/engine.py` | B.0 (allow/deny) |
| Confirmation gate | `daari/policy/confirm.py` | B.1 |
| Config loaders | `daari/config/tools.py` | B.0–B.1 |
| CCS eligibility | `daari/cache/command_context.py` | B.0 |
| `daari context clear` | CLI | B.1 |

### 4. Lt failure behavior

| Case | Behavior |
|------|----------|
| Non-zero exit | Return stderr/stdout in response; **do not** auto-escalate to L3 in B.0 |
| Timeout | Kill subprocess; return timeout error |
| Policy DENY | Never execute; no CCS write |
| Optional explain (B.1+) | If `tools.explain_on_failure: true`, offer L3 summary of stderr — **opt-in** |

## Security

- Default **deny unknown** in B.0 — no arbitrary shell from vague NLP
- Blocklist cannot be overridden by project allowlist
- CCS may contain secrets — redaction + sensitive skip mandatory
- Audit log: `{ policy, command_hash, provider_id, outcome }` — no full stdout in logs by default

## Consequences

**Positive**
- Single place for execution safety review
- Clear split: Lt = permission to run; CCS = permission to remember
- Phased — B.0 shippable with allowlist-only

**Negative**
- Confirmation UX depends on client resending header — awkward in some agents
- Enterprise allowlist maintenance

## Related

- [ADR-0003](0003-tool-native-tier.md) — Lt tier
- [ADR-0008](0008-developer-command-rules-and-context-cache.md) — L2-dev + CCS
- [ADR-0011](0011-pluggable-integration-providers.md) — `integrations.allowed_providers`
- [routing-spec.md](../prd/routing-spec.md) — Lt patterns, DEV-07 re-run
- PRD user stories #14, #60, #73–#77

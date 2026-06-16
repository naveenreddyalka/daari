# ADR-0008: Developer command rules (L2-dev) and command context cache

Date: 2026-06-15  
Status: **accepted**

## Context

daari targets **developers and coding/enterprise workflows**. Many agent prompts are not "generate text" — they are:

- Run a shell command (`git status`, `npm test`)
- Execute a project script (`./scripts/lint.sh`, `make build`)
- Re-ask about output from a command run earlier in the session

Today L2 is generic (templates, regex). Lt executes tools but **command intent detection** and **reusing command output as context** need explicit design.

## Decision

Split developer-facing behavior into three cooperating pieces:

```
L2-dev (detect)  →  Lt (execute)  →  CCS (remember)
     rules              subprocess       command context store
```

### 1. L2-dev — developer command rules (extends L2)

**L2-dev** is a **rules registry tuned for coding workflows** — not a new tier letter, but a **profile** of L2 rules evaluated before generic L2 and before Lt.

| Pattern class | Examples | Routes to |
|---------------|----------|-----------|
| **shell_basic** | `git status`, `git diff`, `npm test`, `pytest`, `gradle build` | Lt → whitelisted command |
| **script_exec** | `run ./scripts/foo.sh`, `execute deploy script` | Lt → script path (validated) |
| **readonly_query** | `show last test output`, `what did lint say` | **CCS read** (no re-run if fresh) |
| **transform** | `convert yaml to json` | L2 generic (no execution) |

Rules are **project-aware** via `.daari/commands.yaml` (optional) — teams can register safe commands for their repo.

### 2. Lt — local execution (unchanged role)

When L2-dev matches with `action: execute`, **Lt** runs the command:

- Subprocess with cwd = project root (from config or detected git root)
- Timeout, output size limits, allowlist/blocklist
- Destructive commands require confirmation ([ADR-0003](0003-tool-native-tier.md))

### 3. CCS — command context store (new cache layer)

**CCS** (Command Context Store) is **not** L0 prompt cache. It stores **execution artifacts** for developer reuse:

```yaml
# Stored at ~/.daari/context/commands/<repo-hash>/<command-hash>.json
command: "npm test"
cwd: "/Users/dev/myproject"
exit_code: 0
stdout_summary: "42 passed"
stdout_full_path: "~/.daari/context/.../stdout.txt"  # truncated/rotated
stderr_summary: ""
ran_at: "2026-06-15T10:00:00Z"
ttl_seconds: 3600
repo_fingerprint: "abc123"
```

**On next request:**

| Scenario | Behavior |
|----------|----------|
| Same command + same cwd within TTL | Return cached output (CCS hit) — **no re-execution** |
| "What did tests show?" / readonly_query | Inject CCS into response context |
| User says `re-run` or TTL expired | Lt executes again; CCS updated |
| Agent needs full output | Attach from `stdout_full_path` or re-run |

CCS feeds **local context** for the next agent turn without calling L3/L6.

### Routing order (updated Phase B+)

```
L0 (prompt response cache)
  → CCS lookup (command context — developer queries)
  → L1 (semantic)
  → L2-dev (developer command rules)
  → L2 (generic rules)
  → Lt (execute command / tool)
  → L3 … L6
```

After Lt execution: **always write CCS**; optionally write L0 if response is cacheable.

## Module placement

| Piece | Module | File area (implementation) |
|-------|--------|----------------------------|
| L2-dev rules | **Rules** | `daari/rules/dev_commands.py` + `.daari/commands.yaml` |
| Lt execution | **Tool executor** | `daari/tools/shell.py` |
| CCS | **Cache** (sub-store) | `daari/cache/command_context.py` |
| Project allowlist | **Config** | `~/.daari/config.yaml` + `.daari/commands.yaml` |

## Phase

| Component | Phase |
|-----------|-------|
| L2-dev basic patterns (git, npm, pytest) | **B.0** (with Lt) |
| CCS read/write | **B.0** |
| `.daari/commands.yaml` per project | **B.1** |
| Enterprise allowlist profiles | **C1** |

## Security

- **Allowlist default** — only known-safe read-only commands without explicit project config
- **Blocklist** — `rm`, `curl | sh`, credential exfil patterns
- **No CCS** for commands marked sensitive (`X-Daari-No-Cache`)
- CCS stdout may contain secrets — respect `.daariignore` / redaction patterns

## Consequences

**Positive**
- Core dev workflow: run locally, remember output, skip redundant runs
- Fine-tuned for coding vs generic chat
- Enterprise can ship team command profiles

**Negative**
- Stale CCS dangerous for `git status`-class commands — TTL required
- Allowlist maintenance burden

## Related

- [ADR-0003](0003-tool-native-tier.md) — Lt execution
- [routing-spec.md](../prd/routing-spec.md) — L2-dev patterns
- PRD user stories #58–61

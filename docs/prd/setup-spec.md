# Setup Module Specification

> **Status:** Draft  
> **Fixes:** Plan review issue #15 (reversibility) + issue #13 (install delivery)  
> **Related:** [PRD](PRD.md) · [ADR-0006](../adr/0006-local-daemon-security.md)

---

## Install delivery

| Phase | Method | Notes |
|-------|--------|-------|
| **Phase A** | `./install.sh` in repo | Checks Python 3.12, venv, Ollama, pulls default model |
| **Phase A.1** | `daari install` CLI command | Same logic as shell script |
| **Future** | `brew install daari` / curl pipe | Requires domain + release artifacts — **not MVP** |

**Removed from MVP claims:** `curl https://daari.dev/install` — domain does not exist yet.

---

## Setup commands

| Command | Phase | Behavior |
|---------|-------|----------|
| **`daari setup`** | **A.1** | **Interactive wizard** — pick clients, models, run doctor (see below) |
| `daari setup cursor` | A.1 | Patch Cursor custom model settings |
| `daari setup models` | A.1 | Pick / map Ollama models to L3 tier (interactive or flags) |
| `daari setup claude-code` | B | Requires Anthropic-compat gateway |
| `daari setup openai-compat` | B | Print env vars for generic SDK |
| `daari setup intellij` | B.1 | Register IntelliJ path for **Lt** tier (not AI client) |
| `daari setup --all` | B | Detect + run applicable recipes (non-interactive) |
| `daari setup --undo <tool>` | A.1 | Restore latest backup for tool |
| `daari doctor` | A.1 | Health check |

---

## Interactive wizard (`daari setup`)

**Yes — users need a guided path.** Not everyone knows what to configure or that IntelliJ is an Lt backend, not an AI client.

Two entry modes (same engine):

| Mode | When |
|------|------|
| **`daari setup`** | First install, exploratory — prompts for choices |
| **`daari setup <tool>`** | Scriptable, docs, CI — skip prompts |

### Wizard flow (Phase A.1)

```
$ daari setup

  daari setup — configure your local stack

  Detected on this machine:
    ✓ Ollama (3 models: llama3.2:3b, llama3.1:8b, …)
    ✓ Cursor
    ✗ IntelliJ IDEA (not found)
    ✗ Claude Code (not supported in this version)

  What do you want to set up?  [Space to select, Enter to confirm]

  ❯ Cursor          — point AI chat at daari (OpenAI-compat)
    Local model     — choose default model for L3 tier
    Run health check — daari doctor after setup
    Skip for now

  → User picks Cursor

  Configure Cursor to use http://127.0.0.1:11435/v1 ?  [Y/n]
  → Backup + patch settings
  → Done. Run: daari serve

  Optional: configure local model now?  [y/N]
  → Lists `ollama list`, user picks default for L3
  → Writes ~/.daari/config.yaml
```

### Phase B+ wizard additions

| Step | Command / screen | Notes |
|------|------------------|-------|
| IntelliJ (Lt) | `daari setup intellij` | Explain: *"Registers IDE for refactor/lint — not your AI chat client"* |
| OpenAI SDK | `daari setup openai-compat` | Print `export OPENAI_BASE_URL=…` |
| Claude Code | `daari setup claude-code` | Only when Anthropic gateway ships (C2) |
| All detected | `daari setup --all` | Non-interactive batch for power users |

### Model selection (`daari setup models`)

```bash
daari setup models              # interactive: ollama list → pick L3 default
daari setup models --tier l3 --model llama3.2:3b   # non-interactive
daari setup models --list       # show current tier → model map
```

- Pulls from **`ollama list`** (live) — not hard-coded
- Phase A.1: L3 only; Phase B adds L4/L5 mapping
- If Ollama missing: wizard offers `ollama pull llama3.2:3b` hint

### Help & discoverability

```bash
daari setup --help              # list subcommands
daari setup cursor --dry-run    # show diff, no writes
daari doctor                    # post-setup: daemon, ollama, cursor endpoint, sample route
```

**Phase A (tracer bullet):** Manual only — [cursor.md](../setup/cursor.md). No wizard yet.

**Phase A.1:** Ship `daari setup` wizard + `daari setup cursor` + `daari setup models` + `daari doctor`.

---

## Reversibility (required)

Every `daari setup <tool>` **must**:

1. **Detect** if tool is installed; exit with message if not
2. **Backup** affected config files to `~/.daari/backups/<tool>/<ISO8601>/`
3. **Apply** changes (patch or write)
4. **Print** summary: files changed, backup path, undo command
5. **Support dry-run:** `daari setup cursor --dry-run` shows diff without writing

### Undo

```bash
daari setup --undo cursor
# Restores most recent backup for cursor; restarts nothing
```

- Keep last **5 backups** per tool; prune older
- Backup manifest: `manifest.json` listing original paths

---

## Cursor recipe (Phase A.1)

**Code:** `daari/clients/cursor/recipe.py`  
**Manual doc:** [cursor.md](../setup/cursor.md)

**Changes:**
- Add custom model pointing to `http://127.0.0.1:11435/v1`
- API key: `daari-local` (or match `DAARI_API_KEY`)

**Manual fallback (Phase A):** Document in `docs/setup/cursor.md` — no automation.

---

## Idempotency

Re-running `daari setup cursor` when already configured:
- Detects existing daari endpoint
- No-op with message, or `--force` to re-apply

---

## Claude Code (Phase B — honest limitation)

Claude Code uses Anthropic API shape. Setup deferred until:
- Anthropic-compat gateway exists (Phase C1), OR
- Claude Code adds OpenAI-compat mode

Document in setup output: *"Claude Code not supported in this version."*

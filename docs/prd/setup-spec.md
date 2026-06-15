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
| `daari setup cursor` | A.1 | Patch Cursor custom model settings |
| `daari setup claude-code` | B | Requires Anthropic-compat gateway |
| `daari setup openai-compat` | B | Print env vars for generic SDK |
| `daari setup intellij` | B | Register IntelliJ path for Lt tier |
| `daari setup --all` | B | Detect + run applicable recipes |
| `daari setup --undo <tool>` | A.1 | Restore latest backup for tool |
| `daari doctor` | A.1 | Health check |

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

**Target file(s):** Cursor user settings (path varies by OS)

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

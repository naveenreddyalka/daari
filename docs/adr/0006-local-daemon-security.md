# ADR-0006: Local daemon security model

Date: 2026-06-15  
Status: **accepted**

## Context

daari runs a local HTTP server receiving prompts that may contain source code and secrets. Plan review low-priority issue: no threat model.

## Decision

### Binding

- **Default:** `127.0.0.1:11435` (configurable port; avoid 11434 Ollama conflict)
- **Never** bind `0.0.0.0` by default
- `--host 0.0.0.0` requires explicit flag + startup warning

### Authentication

| Mode | Default | Notes |
|------|---------|-------|
| Localhost only | No API key required | Trust boundary = local machine |
| Optional API key | `DAARI_API_KEY` env | Clients send `Authorization: Bearer …`; recommended if host != localhost |

### Data at rest

- Cache stored in `~/.daari/cache/` (user-owned)
- Logs in `~/.daari/logs/` with optional redaction (`logging.redact_patterns`)
- Setup backups in `~/.daari/backups/<tool>/<timestamp>/`
- No cloud sync

### Secrets

- Frontier API keys: `~/.daari/config.yaml` or env vars; file mode `0600`
- daari never transmits keys to daari project infrastructure
- Cache excludes requests with `X-Daari-No-Cache` or detected secret patterns (API key regex)

### Telemetry

- **Off by default**
- If added later: opt-in only, documented, OSS client-side batch — no silent phone-home

### Supply chain

- Core dependencies: OSS licenses only (MIT, Apache, BSD)
- Lock file committed (`requirements.txt` or `uv.lock`)
- No remote code execution from config

## Threat model ( proportionate for local dev tool )

| Threat | Mitigation |
|--------|------------|
| LAN attacker hits open port | localhost bind default |
| Malicious cache poisoning | User-local cache; TTL; purge CLI |
| Prompt exfil via frontier | User controls frontier.enabled; logs show L6 |
| Setup script breaks IDE config | Backup before patch; `daari setup --undo` |

## Consequences

- Simple localhost trust model for MVP
- Enterprise/multi-user deployment explicitly out of scope

# Configuration overview

**Outcome:** Know where settings live and how they merge.

## Layers (later wins)

1. Built-in `defaults.yaml`
2. `~/.daari/config.yaml`
3. Profile overlay (`DAARI_PROFILE`)
4. Project `.daari.yaml` (via `X-Daari-Project`)
5. Request headers
6. Environment: `DAARI_<SECTION>__<KEY>`

## Edit safely

- YAML: `~/.daari/config.yaml`
- Config editor API (when `observability.config_editor: true`): `GET/PATCH /v1/daari/config` with `persist: true`
- Web UI config card (`daari web-ui serve`) — send Bearer if API key set

## Major sections

| Section | Purpose |
|---------|---------|
| `server` | host/port, api_key, virtual_keys |
| `models` / `ollama` / `mlx` | Local backends |
| `cache` | L0/L1, disk\|redis |
| `routing` | prefer, confidence, caps |
| `frontier` | L6 providers, budgets, PII |
| `guardrails` / `boundaries` | Safety + product scope |
| `observability` | prometheus, postgres, config_editor |
| `enterprise` | org cache, SSO, policy sync |

Full table: [Config reference](../../reference/config.md) (generated).

## Next

→ [Project profiles](project-profiles.md) · [Auth and keys](auth-and-keys.md)

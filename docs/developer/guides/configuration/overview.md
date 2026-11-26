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

## Reload without restart

After editing `~/.daari/config.yaml` by hand, `POST /v1/daari/reload-config` (admin / master key) or SIGHUP (`kill -HUP <pid>`) on Unix (`server.sighup_reload`, default on; no-op on Windows) re-reads the file and live-applies the same safe subset the config editor owns (routing, budgets, cache TTLs, boundaries, MCP ceilings, observability toggles, …). The response lists `changed_keys` and `requires_restart` — keys like `server.host` / `server.port`, TLS, backends, and store paths still need a restart. Invalid YAML or a rejected value returns **400** and keeps the running settings; in-flight requests are never dropped.

```bash
curl -X POST http://127.0.0.1:11435/v1/daari/reload-config -H "Authorization: Bearer $DAARI_API_KEY"
# {"ok": true, "trigger": "api", "path": "/home/me/.daari/config.yaml",
#  "changed_keys": ["routing.prefer"], "requires_restart": ["server.port"]}
```

## Major sections

| Section | Purpose |
|---------|---------|
| `server` | host/port, api_key, virtual_keys |
| `models` / `ollama` / `mlx` | Local backends |
| `asr` | Local speech-to-text; `frontier_fallback` defaults off ([guide](../backends/asr.md)) |
| `tts` | Local text-to-speech (`POST /v1/audio/speech`); empty `base_url` → 501 ([guide](../backends/tts.md)) |
| `routing.local_pool` | Multi-host pool; `kind: openai` for vLLM / llama.cpp / LM Studio ([vLLM](vllm-local-tier.md), [llama.cpp v1.0+](llamacpp-local-tier.md)) |
| `cache` | L0/L1, disk\|redis |
| `routing` | prefer, confidence, caps |
| `frontier` | L6 providers, budgets, PII |
| `guardrails` / `boundaries` | Safety + product scope |
| `observability` | prometheus, postgres, config_editor |
| `enterprise` | org cache, SSO, policy sync |

Full table: [Config reference](../../reference/config.md) (generated).

## Next

→ [Project profiles](project-profiles.md) · [Auth and keys](auth-and-keys.md) · [vLLM local tier](vllm-local-tier.md) · [llama.cpp local tier](llamacpp-local-tier.md)

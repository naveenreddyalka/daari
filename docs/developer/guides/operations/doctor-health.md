# Doctor and health probes

**Outcome:** Confirm daemon and backends are healthy.

## Steps

```bash
curl -fsS http://127.0.0.1:11435/health   # {"status":"ok","version":"…"}
curl -fsS http://127.0.0.1:11435/ready
daari --version
daari doctor
daari doctor --suggest-models   # VRAM-aware stack advice
```

Orchestrators should use `/ready` (Ollama + cache handles), not only `/health`.
`/health` stays a liveness probe (`status=ok`) and now also reports the running
package `version` for upgrade/rollback discovery.

## Troubleshoot

| Probe | Failure meaning |
|-------|-----------------|
| `/health` | Process not listening |
| `/ready` | Dependency (Ollama/cache) not ready |
| doctor `redis` | Optional: when `cache.backend=redis`, PING `cache.redis_url` — timeout/unreachable means shared L0/rate-limit counters are dark |
| doctor `ready` | Optional: when the daemon answers, `GET /ready` — warn on `degraded` / `not_ready` (same signal as kube probes) |
| doctor `metrics_auth` | Optional: when the daemon answers, prometheus is on, and `server.api_key` is set — unauthenticated `GET /metrics` returning 401 means scrapers need Bearer / Helm `serviceMonitor.bearerTokenSecret` (or `observability.metrics_port`) |
| doctor mlx | Optional backend misconfigured |
| doctor `asr` | Optional: `asr.base_url` unreachable, or `asr.frontier_fallback` with frontier disabled / no API key. Empty ASR config is quiet (the route returns 501) |
| doctor `tts` | Optional: `tts.base_url` unreachable. Empty TTS config is quiet (POST `/v1/audio/speech` returns 501) |
| doctor `images_generations` | Optional: when `frontier.enabled` and a key resolves, dry-checks OpenAPI for `POST /v1/images/generations`; frontier on without a key warns that the route returns 501. Frontier off skips quietly |
| doctor `ocr` | Optional: both `ocr.base_url` and `ocr.vision_model` unset — `POST /v1/ocr` falls through to frontier L6; tip points at [clients-and-gateways.md](../../concepts/clients-and-gateways.md) / config.md |
| doctor `decisions` | Optional: `systemone.enabled=false` and/or frontier on without an API key — `POST /v1/decisions` lacks a local (clef/nimble/tev1) or gpt-6-luna path; tip points at clients-and-gateways / http-api |
| doctor `policy_status` | Optional: when `enterprise.policy_sync_url` is set, warns if policy-sync never applied; ok detail includes last hash — same signal as `daari enterprise policy-status` |
| doctor `cors_origins` | Optional: empty allowlist is an advisory tip for `daari web-ui` (`http://127.0.0.1:11437`); a non-empty list that omits that origin (or `DAARI_WEB_UI_ORIGIN`) warns — browsers will block credentialed dashboard calls |
| doctor `request_deadline` | Optional: `upstream.request_deadline_seconds` unset or `<= 0` — per-tier timeouts only; set a positive budget (or send `X-Daari-Deadline-Ms`) so escalation stops with 504 |
| doctor `local_pool_frontier_fallback` | Optional: `routing.local_pool.frontier_fallback` true while `frontier.enabled` is false |

| doctor `otlp_logs` | Optional: `observability.otlp_logs` true without `OTEL_EXPORTER_OTLP_ENDPOINT` — log export is a silent no-op |
| doctor `fleet_artifacts` | Optional: fleet signals (`DAARI_FLEET_REPLICAS` > 1, `cache.backend=redis`, or `observability.backend=postgres`) with sqlite `batches` / `files` / `responses` / ledger / `enterprise.audit_backend` — split-brain, 404, or incomplete audit-export risk |
| doctor `fleet_cache` | Optional: `DAARI_FLEET_REPLICAS` > 1 without `cache.backend=redis` — L0 / session pins / singleflight stay per-pod |
| doctor `scoped_cache_fleet` | Optional: `DAARI_FLEET_REPLICAS` > 1 with `cache.backend` not `redis` and any virtual key/team `cache_scope` other than `global` — tenant L0/L1 stays per-pod |
| doctor `soft_budget_ratio` | Optional: `frontier.soft_budget_ratio=0` while request quotas, USD budget windows, or `rate_limit` RPM/TPM are set — soft 402/429 warnings disabled |
| doctor `budget_webhook_secret` | Optional: `alerts.budget_webhook_url` set without `alerts.budget_webhook_secret` — spoofable pages |
| doctor `helm_image_tag` | Optional: checkout `deploy/helm/daari/values.yaml` `image.tag` behind the running package version |
| doctor `backup` | Optional: no recent archive under `~/.daari/backups`, or recent backups are all **plaintext** — tip suggests `daari backup create … --encrypt openssl` (or `age`); see [backup-restore.md](backup-restore.md#optional-encryption-1176) |
| doctor `header_policy` | Optional: `server.header_policy.enabled` is true but `required` / `deny` / `allow` are empty — enable at least one rule or set `enabled: false`; see [auth-and-keys.md](../configuration/auth-and-keys.md#header-policy-pre-auth) |
| doctor `mcp_require_key_access` | Optional: when `integrations.mcp_policy.require_key_access_defined` is true — tip that virtual keys without `metadata.mcp` allow/deny/servers fail initialize, get empty tools/list, and tools/call deny; master key unchanged |
| doctor `mcp_registry` | Optional: when `integrations.mcp_registry.enabled` is true — tip that `GET /v1/mcp/registry.json` is advertised (auth-agnostic) while `/mcp` still enforces API-key / allowlists |
| doctor `mcp_aggregate_egress` | Optional: when `integrations.mcp_aggregate_egress.enabled` is true — tip that egress `mcp_servers` merge into `/mcp` tools/list as `{server_id}__{tool}` with policy/SSRF still enforced |
| doctor `mcp_oauth_local_as` | Optional: when `integrations.mcp_oauth.local_as` is true — tip that `POST /oauth/token` mints Bearers while `/mcp` still requires auth |
| doctor `mcp_token_exchange` | Optional: when any `integrations.mcp_servers` entry uses `auth_type: oauth2_token_exchange` — tip that inbound Bearer is exchanged (RFC 8693) before egress; SSRF + fail-closed on missing subject / exchange errors |
| doctor `master_key_strength` | Optional: warns when `server.dangerously_permit_weak_or_unset_api_key` is true, or when master key is unset while virtual keys / `mcp_oauth.local_as` imply auth (#1320) |
| doctor `config_editor_ungoverned` | Optional: when `observability.config_editor` is on, SSO is off, and no master key is set — tip that `PATCH /v1/daari/config` (and other admin surfaces) are ungoverned (#1441) |
| doctor `decision_classifier` | Optional: when `routing.decision_classifier.enabled` is true — tip that an Ollama `/v1/systemone` difficulty hop runs before heuristic tier pick (fallback on timeout/failure) |
| doctor `compact_to_fit` | Optional: when `routing.compact_to_fit.enabled` is true — tip that oldest droppable turns are trimmed before L6/frontier; system and tool-call payloads are kept; over-cap history fail-closes oversized; successful trims expose `tokens_before` / `tokens_after` and `compact_to_fit_tokens_dropped` |
| doctor `structured_json_logs` | Optional: when `observability.structured_json_logs` is true — tip that gateway events are single-line JSON on stdout (containers/SIEM); `~/.daari/cursor-requests.log` is still written |
| doctor `decision_classifier_model` | Optional: when the classifier is enabled but `routing.decision_classifier.model` (default `nimble`) is missing from Ollama `/api/tags` — tip to `ollama pull <model>`; quiet if Ollama is unreachable (the `ollama` check owns that) |

## Next

→ [Docker Compose](docker-compose.md)

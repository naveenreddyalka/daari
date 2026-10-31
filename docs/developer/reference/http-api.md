# HTTP API reference

Generated from the FastAPI OpenAPI schema — do not edit by hand.

OpenAPI version: 3.1.0 · daari gateway on `127.0.0.1:11435` by default.

| Method | Path | Summary |
|--------|------|---------|
| `POST` | `/api/chat` | Chat |
| `POST` | `/api/embed` | Embed |
| `POST` | `/api/embeddings` | Embeddings |
| `POST` | `/api/generate` | Generate |
| `GET` | `/api/ps` | Ps |
| `POST` | `/api/show` | Show |
| `GET` | `/api/tags` | Tags |
| `GET` | `/api/version` | Version |
| `GET` | `/health` | Health |
| `POST` | `/introspect` | Introspect |
| `POST` | `/mcp` | Mcp Jsonrpc |
| `POST` | `/mcp/proxy` | Mcp Proxy |
| `GET` | `/metrics` | Prometheus Metrics |
| `GET` | `/ready` | Ready |
| `POST` | `/v1/audio/speech` | Audio Speech |
| `POST` | `/v1/audio/transcriptions` | Audio Transcriptions |
| `POST` | `/v1/audio/translations` | Audio Translations |
| `GET` | `/v1/audio/voices` | Audio Voices |
| `GET` | `/v1/batches` | List Batches |
| `POST` | `/v1/batches` | Create Batch |
| `GET` | `/v1/batches/{batch_id}` | Retrieve Batch |
| `POST` | `/v1/batches/{batch_id}/cancel` | Cancel Batch |
| `POST` | `/v1/chat/completions` | Chat Completions |
| `GET` | `/v1/daari/anthropic/enforcement` | Daari Anthropic Enforcement |
| `GET` | `/v1/daari/audit` | Daari Audit List |
| `POST` | `/v1/daari/breakers/reset` | Daari Breakers Reset |
| `GET` | `/v1/daari/cache/diversity` | Daari Cache Diversity |
| `POST` | `/v1/daari/cache/invalidate` | Daari Cache Invalidate |
| `GET` | `/v1/daari/config` | Daari Config Get |
| `PATCH` | `/v1/daari/config` | Daari Config Patch |
| `GET` | `/v1/daari/events` | Daari Events List |
| `POST` | `/v1/daari/feedback` | Daari Feedback |
| `GET` | `/v1/daari/keys` | Daari Keys List |
| `POST` | `/v1/daari/keys/unlock` | Daari Keys Unlock |
| `GET` | `/v1/daari/learn/stats` | Daari Learn Stats |
| `GET` | `/v1/daari/lockouts` | Daari Lockouts List |
| `GET` | `/v1/daari/mcp/activity` | Daari Mcp Activity List |
| `POST` | `/v1/daari/mcp/activity/{request_id}/abort` | Daari Mcp Activity Abort |
| `POST` | `/v1/daari/reload-caches` | Daari Reload Caches |
| `GET` | `/v1/daari/report` | Daari Report |
| `GET` | `/v1/daari/route/preview` | Daari Route Preview Get |
| `POST` | `/v1/daari/route/preview` | Daari Route Preview Post |
| `GET` | `/v1/daari/spend/export` | Daari Spend Export |
| `GET` | `/v1/daari/spend/report` | Daari Spend Report |
| `POST` | `/v1/daari/sso/session` | Daari Sso Session |
| `GET` | `/v1/daari/stats` | Daari Stats |
| `POST` | `/v1/daari/systemone/breaker/reset` | Daari Systemone Breaker Reset |
| `GET` | `/v1/daari/teams` | Daari Teams List |
| `GET` | `/v1/daari/traces` | Daari Traces |
| `GET` | `/v1/daari/traces/{trace_id}` | Daari Trace Detail |
| `POST` | `/v1/daari/webhooks/anthropic/org` | Daari Anthropic Org Webhook |
| `POST` | `/v1/decisions` | Decisions |
| `POST` | `/v1/embeddings` | Embeddings |
| `GET` | `/v1/files` | List Files |
| `POST` | `/v1/files` | Upload File |
| `DELETE` | `/v1/files/{file_id}` | Delete File |
| `GET` | `/v1/files/{file_id}` | Retrieve File |
| `GET` | `/v1/files/{file_id}/content` | Download File Content |
| `POST` | `/v1/images/edits` | Images Edits |
| `POST` | `/v1/images/generations` | Images Generations |
| `POST` | `/v1/images/variations` | Images Variations |
| `POST` | `/v1/mcp/query` | Mcp Query |
| `GET` | `/v1/mcp/registry.json` | Mcp Registry |
| `POST` | `/v1/messages` | Messages |
| `POST` | `/v1/messages/count_tokens` | Count Tokens |
| `GET` | `/v1/messages/health` | Health |
| `POST` | `/v1/messages/moderations` | Messages Moderations |
| `GET` | `/v1/models` | List Models |
| `GET` | `/v1/models/{model_id}` | Retrieve Model |
| `POST` | `/v1/moderations` | Moderations |
| `POST` | `/v1/ocr` | Ocr |
| `POST` | `/v1/org-learning/sync` | Org Learning Sync |
| `POST` | `/v1/rerank` | Rerank |
| `POST` | `/v1/responses` | Responses |
| `POST` | `/v1/responses/compact` | Compact Response |
| `POST` | `/v1/responses/input_tokens` | Input Tokens |
| `DELETE` | `/v1/responses/{response_id}` | Delete Response |
| `GET` | `/v1/responses/{response_id}` | Get Response |
| `POST` | `/v1/responses/{response_id}/cancel` | Cancel Response |
| `POST` | `/v1/systemone` | Systemone |

## Admin keys / teams inventory

`GET /v1/daari/keys` and `GET /v1/daari/teams` (admin / master key) return redacted rows plus pagination metadata: query `limit` (default **100**, max **500**), `offset` (default **0**), and optional `team_id`. Response includes `total`, `has_more`, `limit`, and `offset`. A caller pinned to a team who requests a different `team_id` receives **403**. Omitting `team_id` keeps the full inventory for an unscoped admin. Successful reads emit `admin.keys.list` / `admin.teams.list` audit events (`limit` / `offset` / `total` / `returned` / `team_id` — never secrets). `GET /v1/daari/audit` accepts the same optional `team_id` and returns only rows whose detail includes that id (`total` / `has_more` match the filtered set). `GET /v1/daari/events` records `admin.events.list` (actor, role, limit, team scope, returned count; event bodies are not copied).

## Request / event log

`GET /v1/daari/events` (analyst / master, or a virtual key on the same read floor as other `/v1/daari` reads) lists newest-first gateway events when `observability.request_log.backend=postgres`. Query `limit` (default **100**, max **1000**), `offset`, or exclusive `cursor` (event id), plus optional `team_id`, `key_id`, and `kind` (event name). JSONL-only installs return **501**. `daari events list` reads the same store (`--team`, `--kind`, `--limit`, `--cursor`).

## Key lockouts

`GET /v1/daari/lockouts` (analyst / admin / master) lists currently locked key prefixes as `{prefix, expires_in_seconds}` and records `admin.lockouts.list` (returned count and prefixes; no secrets). `POST /v1/daari/keys/unlock` remains admin-only. `daari keys lockouts` prints the same inventory.

## Config editor ownership

`GET` / `PATCH /v1/daari/config` (when `observability.config_editor` is on) expose per-field `ownership` (`source` / `editable` / `diverged`) for the safe subset, including `routing.decision_classifier.*`, `routing.compact_to_fit.*`, `routing.signal_overrides` (full list replacement), `systemone.base_url`, `observability.structured_json_logs`, `observability.team_metrics`, and MCP knobs (`integrations.mcp_oauth.local_as` / `protected_resource`, `integrations.mcp_aggregate_egress.enabled`, `integrations.mcp_registry.enabled`, `integrations.mcp_policy.require_key_access_defined`, `integrations.mcp_servers` as `{id, rpm, tpm}` ceiling rows). Secrets such as `integrations.mcp_oauth.signing_secret` and MCP server tokens stay non-editable and are omitted from the payload.

**Auth:** With SSO off and a master key set, `PATCH` (and other admin surfaces) require the master key — virtual keys get **403**. `GET` keeps viewer-style read access for virtual keys (safe subset only). With SSO on, role gates apply (`analyst` for GET, `admin_min_role` for PATCH). With no master key (sandbox hatch), writes stay open; `daari doctor` warns that the config editor is ungoverned.

## Traces compact_to_fit

`GET /v1/daari/traces` and `GET /v1/daari/traces/{trace_id}` include a `compact_to_fit` step with `tokens_before` / `tokens_after` when a compact-to-fit trim actually ran (no step when the message count is unchanged). Clients that skip `X-Daari-Meta` still see those FinOps fields on the trace.

## Responses stream resume

`GET /v1/responses/{response_id}` accepts query parameters:

- `stream` — when `true`, replay stored terminal output as Responses SSE with contiguous `sequence_number` (from 0) on every non-keepalive event
- `starting_after` — skip events with sequence ≤ this value (past-the-end resume is an empty stream)

When `starting_after` is omitted, a non-negative integer `Last-Event-ID` header is treated the same way (invalid/negative values are ignored → resume from 0); an explicit query param wins over the header.

Non-terminal (in-flight / `queued`) responses return **409** when `stream=true`. Plain GET (no `stream`) remains JSON.

## Decisions

`POST /v1/decisions` accepts the OpenAI Decisions GA shape: optional top-level `input_json` (or `input_json` content parts inside `input`), per-question `instructions` as a string or content-part array (including images), and up to **400** questions per request. Local catalog models fold structured evidence into systemone `state`/`images`; `gpt-6-luna` forwards the GA payload to the frontier. Frontier billing is input-only with shared-input cache discounts ($0.10/1M input, $0.01/1M cached). Honors `Idempotency-Key`.

## Systemone

`POST /v1/systemone` proxies Ollama decision models. The body accepts optional `images` (list of base64 strings, Ollama 0.35.1+ Clef multimodal) forwarded verbatim when present; omit the field for text-only scoring. Honors `Idempotency-Key` with the same replay / 409 conflict / in-flight wait semantics as `POST /v1/decisions`.

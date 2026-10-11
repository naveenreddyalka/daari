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
| `GET` | `/v1/batches` | List Batches |
| `POST` | `/v1/batches` | Create Batch |
| `GET` | `/v1/batches/{batch_id}` | Retrieve Batch |
| `POST` | `/v1/batches/{batch_id}/cancel` | Cancel Batch |
| `POST` | `/v1/chat/completions` | Chat Completions |
| `GET` | `/v1/daari/audit` | Daari Audit List |
| `GET` | `/v1/daari/cache/diversity` | Daari Cache Diversity |
| `POST` | `/v1/daari/cache/invalidate` | Daari Cache Invalidate |
| `GET` | `/v1/daari/config` | Daari Config Get |
| `PATCH` | `/v1/daari/config` | Daari Config Patch |
| `POST` | `/v1/daari/feedback` | Daari Feedback |
| `GET` | `/v1/daari/keys` | Daari Keys List |
| `GET` | `/v1/daari/learn/stats` | Daari Learn Stats |
| `GET` | `/v1/daari/mcp/activity` | Daari Mcp Activity List |
| `POST` | `/v1/daari/mcp/activity/{request_id}/abort` | Daari Mcp Activity Abort |
| `POST` | `/v1/daari/reload-caches` | Daari Reload Caches |
| `GET` | `/v1/daari/report` | Daari Report |
| `GET` | `/v1/daari/route/preview` | Daari Route Preview Get |
| `POST` | `/v1/daari/route/preview` | Daari Route Preview Post |
| `POST` | `/v1/daari/sso/session` | Daari Sso Session |
| `GET` | `/v1/daari/stats` | Daari Stats |
| `GET` | `/v1/daari/teams` | Daari Teams List |
| `GET` | `/v1/daari/traces` | Daari Traces |
| `GET` | `/v1/daari/traces/{trace_id}` | Daari Trace Detail |
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

`GET /v1/daari/keys` and `GET /v1/daari/teams` (admin / master key) return redacted rows plus pagination metadata: query `limit` (default **100**, max **500**) and `offset` (default **0**); response includes `total`, `has_more`, `limit`, and `offset`. Successful reads emit `admin.keys.list` / `admin.teams.list` audit events (`limit` / `offset` / `total` / `returned` — never secrets).

## Config editor ownership

`GET` / `PATCH /v1/daari/config` (when `observability.config_editor` is on) expose per-field `ownership` (`source` / `editable` / `diverged`) for the safe subset, including `routing.decision_classifier.*`, `routing.compact_to_fit.*`, `observability.structured_json_logs`, and MCP knobs (`integrations.mcp_oauth.local_as` / `protected_resource`, `integrations.mcp_aggregate_egress.enabled`, `integrations.mcp_registry.enabled`, `integrations.mcp_policy.require_key_access_defined`). Secrets such as `integrations.mcp_oauth.signing_secret` stay non-editable and are omitted from the payload.

**Auth:** With SSO off and a master key set, `PATCH` (and other admin surfaces) require the master key — virtual keys get **403**. `GET` keeps viewer-style read access for virtual keys (safe subset only). With SSO on, role gates apply (`analyst` for GET, `admin_min_role` for PATCH). With no master key (sandbox hatch), writes stay open; `daari doctor` warns that the config editor is ungoverned.

## Traces compact_to_fit

`GET /v1/daari/traces` and `GET /v1/daari/traces/{trace_id}` include a `compact_to_fit` step with `tokens_before` / `tokens_after` when a compact-to-fit trim actually ran (no step when the message count is unchanged). Clients that skip `X-Daari-Meta` still see those FinOps fields on the trace.

## Responses stream resume

`GET /v1/responses/{response_id}` accepts query parameters:

- `stream` — when `true`, replay stored terminal output as Responses SSE with contiguous `sequence_number` (from 0) on every non-keepalive event
- `starting_after` — skip events with sequence ≤ this value (past-the-end resume is an empty stream)

When `starting_after` is omitted, a non-negative integer `Last-Event-ID` header is treated the same way (invalid/negative values are ignored → resume from 0); an explicit query param wins over the header.

Non-terminal (in-flight / `queued`) responses return **409** when `stream=true`. Plain GET (no `stream`) remains JSON.

## Systemone

`POST /v1/systemone` proxies Ollama decision models. The body accepts optional `images` (list of base64 strings, Ollama 0.35.1+ Clef multimodal) forwarded verbatim when present; omit the field for text-only scoring.

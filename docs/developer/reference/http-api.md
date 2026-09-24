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
| `GET` | `/v1/daari/learn/stats` | Daari Learn Stats |
| `POST` | `/v1/daari/reload-caches` | Daari Reload Caches |
| `GET` | `/v1/daari/report` | Daari Report |
| `GET` | `/v1/daari/route/preview` | Daari Route Preview Get |
| `POST` | `/v1/daari/route/preview` | Daari Route Preview Post |
| `POST` | `/v1/daari/sso/session` | Daari Sso Session |
| `GET` | `/v1/daari/stats` | Daari Stats |
| `GET` | `/v1/daari/traces` | Daari Traces |
| `GET` | `/v1/daari/traces/{trace_id}` | Daari Trace Detail |
| `POST` | `/v1/embeddings` | Embeddings |
| `GET` | `/v1/files` | List Files |
| `POST` | `/v1/files` | Upload File |
| `DELETE` | `/v1/files/{file_id}` | Delete File |
| `GET` | `/v1/files/{file_id}` | Retrieve File |
| `GET` | `/v1/files/{file_id}/content` | Download File Content |
| `POST` | `/v1/mcp/query` | Mcp Query |
| `POST` | `/v1/messages` | Messages |
| `POST` | `/v1/messages/count_tokens` | Count Tokens |
| `GET` | `/v1/messages/health` | Health |
| `GET` | `/v1/models` | List Models |
| `GET` | `/v1/models/{model_id}` | Retrieve Model |
| `POST` | `/v1/moderations` | Moderations |
| `POST` | `/v1/org-learning/sync` | Org Learning Sync |
| `POST` | `/v1/rerank` | Rerank |
| `POST` | `/v1/responses` | Responses |
| `POST` | `/v1/responses/input_tokens` | Input Tokens |
| `DELETE` | `/v1/responses/{response_id}` | Delete Response |
| `GET` | `/v1/responses/{response_id}` | Get Response |
| `POST` | `/v1/responses/{response_id}/cancel` | Cancel Response |

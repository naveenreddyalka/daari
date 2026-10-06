# Configuration reference

Generated from the pydantic settings model — do not edit by hand.

Keys live in `~/.daari/config.yaml` (nested YAML), can be overridden per-project
in `.daari.yaml`, and every key is also settable via environment variable:
`DAARI_<SECTION>__<KEY>` (double underscore per nesting level).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `server.host` | str | `'127.0.0.1'` |  |
| `server.port` | int | `11435` |  |
| `server.api_key` | str | list[str] | `''` |  |
| `server.dangerously_permit_weak_or_unset_api_key` | bool | `False` | When true, ``daari serve`` allows an empty or denylisted master key (sk-1234 / changeme / daari-local / …) for hermetic tests and local sandboxes (#1320). Default false refuses before bind. Env: DAARI_SERVER__DANGEROUSLY_PERMIT_WEAK_OR_UNSET_API_KEY. |
| `server.virtual_keys.enabled` | bool | `True` |  |
| `server.virtual_keys.path` | str | `'~/.daari/auth/virtual-keys.sqlite3'` |  |
| `server.virtual_keys.backend` | Literal | `'sqlite'` | sqlite (default) or postgres (observability.postgres_url) so keys and teams resolve across replicas (#544). Env: DAARI_SERVER__VIRTUAL_KEYS__BACKEND. |
| `server.max_body_bytes` | int | `10485760` | Hard cap on inbound request body size (#933). Oversized requests return 413 before the body is buffered. 0 disables the cap. File/audio upload routes may use a higher floor so files.max_total_bytes still applies. Env: DAARI_SERVER__MAX_BODY_BYTES. |
| `server.header_policy.enabled` | bool | `False` | When true, evaluate required/deny/allow before require_api_key. Env: DAARI_SERVER__HEADER_POLICY__ENABLED. |
| `server.header_policy.required` | list | `[]` | Header names that must be present and non-empty. |
| `server.header_policy.deny` | list | `[]` | Denylist rules (exact and/or regex) evaluated against headers. |
| `server.header_policy.allow` | dict | `{}` | Optional allowlists keyed by header name. When the header is present, its value must be one of the listed strings. |
| `server.tls.cert_file` | str | `''` | PEM certificate path (or secret:// ref). Env: DAARI_SERVER__TLS__CERT_FILE. |
| `server.tls.key_file` | str | `''` | PEM private key path or secret:// ref. Env: DAARI_SERVER__TLS__KEY_FILE. |
| `server.tls.client_ca` | str | `''` | Optional client CA path/ref; when set, require a valid client cert (mTLS). Env: DAARI_SERVER__TLS__CLIENT_CA. |
| `server.cors_origins` | list | `[]` | Browser Origin allowlist for CORS (#938). Empty disables CORS middleware. When set, enables ACAO for listed origins, Authorization header, and OPTIONS preflight. Env: DAARI_SERVER__CORS_ORIGINS (JSON list, e.g. '["http://127.0.0.1:11437"]'). |
| `server.security_headers` | bool | `True` | Attach baseline security headers on every response (#938): X-Content-Type-Options: nosniff, X-Frame-Options: DENY, Referrer-Policy: no-referrer. Env: DAARI_SERVER__SECURITY_HEADERS. |
| `server.sse_keepalive_seconds` | float | `10.0` | Idle seconds between streamed chunks before emitting a keepalive frame for the entire stream lifetime (#972) (SSE comment `: keepalive` on OpenAI/Anthropic/Responses routes, a blank line on the NDJSON Ollama facade). Keeps proxies and SDK read timeouts from dropping slow streams (including mid-generation pauses). 0 disables. |
| `server.stream_idle_timeout_seconds` | float | `0.0` | If upstream produces no chunk for this many seconds mid-stream, end with an in-band error event instead of hanging (#972). 0 disables (default). |
| `server.graceful_timeout_seconds` | float | `30.0` | Seconds uvicorn waits for in-flight requests (including SSE) after SIGTERM/SIGINT before force-closing (#1104). Wire via `daari serve --graceful-timeout` or DAARI_SERVER__GRACEFUL_TIMEOUT_SECONDS. Size terminationGracePeriodSeconds above this plus preStop sleep. |
| `auth.throttle_enabled` | bool | `True` | When false, invalid-key attempts are never rate-limited. |
| `auth.max_failures` | int | `10` | Invalid-key failures per client IP within window_seconds before 429. 0 disables the counter. Env: DAARI_AUTH__MAX_FAILURES. |
| `auth.window_seconds` | float | `60.0` | Sliding window for auth.max_failures. Env: DAARI_AUTH__WINDOW_SECONDS. |
| `auth.exempt_loopback` | bool | `True` | Skip throttling for 127.0.0.1 / ::1 / localhost. |
| `secrets.refresh_ttl_seconds` | float | `300.0` | TTL for re-resolving env-file/exec/keychain secret:// refs at use time. 0 = resolve once at boot (legacy). Default 300s. Env-file refs also re-resolve when the source file mtime changes. Env: DAARI_SECRETS__REFRESH_TTL_SECONDS. |
| `rate_limit.rpm` | int | `0` | Default requests per minute per key (0=unlimited). |
| `rate_limit.tpm` | int | `0` | Default tokens per minute per key (0=unlimited). |
| `rate_limit.model_rpm` | int | `0` | Per-key-per-model RPM. 0 falls back to rpm. |
| `rate_limit.model_tpm` | int | `0` | Per-key-per-model TPM. 0 falls back to tpm. |
| `rate_limit.max_in_flight` | int | `0` | Global in-flight request cap. 0 disables the concurrency gate. |
| `rate_limit.queue_size` | int | `32` | Waiters allowed when in-flight is full; overflow is 503 + Retry-After. |
| `rate_limit.retry_after_seconds` | int | `1` | Retry-After value on 429/503. |
| `rate_limit.fail_open` | bool | `False` | When Redis counters are unreachable, allow requests without counting instead of degrading to the per-replica SQLite backend. Default false (prefer SQLite fallback so limits still apply locally). |
| `models.l3` | str | `'llama3.2:3b'` |  |
| `models.l4` | str | `'llama3.1:8b'` |  |
| `models.l5` | str | `'llama3.1:70b'` |  |
| `models.weights` | dict | `{}` |  |
| `models.capabilities` | dict | `{}` |  |
| `models.timeout_s` | dict | `{}` | Optional per-tier request timeout in seconds (keys L3/L4/L5). Unset tiers use `upstream.local_timeout_seconds`. |
| `ollama.base_url` | str | `'http://127.0.0.1:11434'` |  |
| `systemone.enabled` | bool | `True` | When true, POST /v1/systemone proxies to ollama.base_url. When false, the route returns 501 not_implemented. |
| `mlx.enabled` | bool | `False` |  |
| `mlx.base_url` | str | `'http://127.0.0.1:11440'` |  |
| `mlx.models` | dict | `{}` |  |
| `asr.base_url` | str | `''` | OpenAI-compatible ASR base URL, including /v1 (vLLM, whisper.cpp server, or another local pool member). Empty leaves POST /v1/audio/transcriptions unconfigured. |
| `asr.model` | str | `''` | Optional model name sent to the ASR server. When set, it replaces the client model so a local server always sees its own id. |
| `asr.frontier_fallback` | bool | `False` | When true and asr.base_url is empty, forward one transcription to the configured frontier base if frontier.enabled and a key is present. Default false so audio is never uploaded to a cloud endpoint implicitly. |
| `ocr.base_url` | str | `''` | OpenAI-/Mistral-compatible OCR API root, including /v1. When set, POST /v1/ocr forwards to {base_url}/ocr. Empty falls through to ocr.vision_model or frontier L6. |
| `ocr.model` | str | `''` | Optional default OCR model id when the client omits model. Used for local base_url and frontier passthrough. |
| `ocr.vision_model` | str | `''` | When base_url is empty, run OCR via local Ollama multimodal chat at ollama.base_url using this vision model (image_url / image data URIs). Empty skips the local vision path. |
| `tts.base_url` | str | `''` | OpenAI-compatible TTS base URL, including /v1 (openedai-speech, Kokoro-FastAPI, or similar). Empty leaves POST /v1/audio/speech unconfigured. |
| `tts.model` | str | `''` | Optional model name sent to the TTS server. When set, it replaces the client model so a local server always sees its own id. |
| `tts.voice` | str | `''` | Optional default voice when the request omits voice (OpenAI alloy/echo/… or the local server's voice id). |
| `cache.l0.enabled` | bool | `True` |  |
| `cache.l0.path` | str | `'~/.daari/cache/l0'` |  |
| `cache.l0.ttl_seconds` | float | `0.0` |  |
| `cache.l1.enabled` | bool | `True` |  |
| `cache.l1.path` | str | `'~/.daari/cache/l1'` |  |
| `cache.l1.similarity_threshold` | float | `0.88` |  |
| `cache.l1.draft_threshold` | float | `0.75` |  |
| `cache.l1.max_entries` | int | `1000` |  |
| `cache.l1.embedding_model` | str | `'nomic-embed-text'` |  |
| `cache.l1.ttl_seconds` | float | `0.0` |  |
| `cache.l1.embed_cache_size` | int | `512` |  |
| `cache.l1.normalize_inputs` | bool | `True` |  |
| `cache.l1.verify` | Literal | `'lexical'` | Second-stage check before serving a semantic hit, because a cosine threshold alone cannot separate a paraphrase from a near-miss. `none` serves any hit above the threshold; `lexical` (default) vetoes hits whose numbers, units, or negation differ; `model` additionally asks a local model to confirm equivalence. |
| `cache.l1.shadow_sample_rate` | float | `0.05` |  |
| `cache.backend` | Literal | `'disk'` |  |
| `cache.redis_url` | str | `'redis://127.0.0.1:6379/0'` |  |
| `cache.redis_prefix` | str | `'daari:l0:'` |  |
| `cache.redis_l1_prefix` | str | `'daari:l1:'` |  |
| `cache.redis_timeout_seconds` | float | `2.0` | socket_connect_timeout and socket_timeout for every Redis client (rate-limit counters, L0/L1 cache, budget-alert dedupe). Keeps a hung Redis from blocking gateway requests indefinitely (#463). |
| `routing.prefer` | Literal | `'balanced'` |  |
| `routing.confidence_threshold` | float | `0.7` |  |
| `routing.category_policies` | dict | `{}` |  |
| `routing.max_tier_for_chat` | Optional | `None` |  |
| `routing.latency_budget_ms` | int | `0` |  |
| `routing.warm_model_preference` | bool | `True` |  |
| `routing.ttft_aware` | bool | `False` | When true, after the heuristic pick, prefer a faster local tier (L3..heuristic) with enough recent TTFT samples and a lower configured percentile. Default off. |
| `routing.ttft_percentile` | float | `0.95` | TTFT histogram percentile used when ttft_aware is true. |
| `routing.ttft_min_samples` | int | `20` | Minimum TTFT samples per tier before ttft_aware may prefer it. |
| `routing.learned_router` | bool | `False` |  |
| `routing.reasoning_effort_escalation` | bool | `False` |  |
| `routing.compact_to_fit.enabled` | bool | `False` | When true, chat history is compacted to max_messages / max_tokens before L6. System messages and tool-call payloads are never deleted; if the remainder still exceeds the cap, history is left oversized (fail closed). A successful trim records tokens_before / tokens_after on the compact_to_fit trace step and increments compact_to_fit_tokens_dropped on /v1/daari/stats. Default off. Editable via GET/PATCH /v1/daari/config ownership (config editor). |
| `routing.compact_to_fit.max_messages` | int | `32` | Keep at most this many messages when compact_to_fit is on. Positive integer. Editable via config editor ownership. |
| `routing.compact_to_fit.max_tokens` | int | `0` | Approximate token budget (chars/4) when compact_to_fit is on. 0 disables the token cap. Non-negative integer. Editable via config editor ownership. |
| `routing.stall_escalation.enabled` | bool | `False` | When true, N identical tool calls in the last window, or N consecutive error tool results, escalate the chosen tier by one. Default off. |
| `routing.stall_escalation.repeats` | int | `3` | Identical calls or consecutive error results required to stall. |
| `routing.stall_escalation.window` | int | `6` | How many recent tool calls are inspected for identical repeats. |
| `routing.phase_routing.enabled` | bool | `False` | When true, the last window of tool-call names classifies the turn as explore / implement / verify and adjusts the heuristic tier. Default off. |
| `routing.phase_routing.window` | int | `6` | How many recent tool-call names are classified for phase. |
| `routing.phase_routing.explore` | int | str | `-1` | Tier adjustment for explore-phase turns. Default -1 (floor L3). |
| `routing.phase_routing.implement` | int | str | `0` | Tier adjustment for implement-phase turns. Default 0. |
| `routing.phase_routing.verify` | int | str | `0` | Tier adjustment for verify-phase turns. Default 0. |
| `routing.decision_classifier.enabled` | bool | `False` | When true, Ask (and optionally Agent) turns call Ollama /v1/systemone before the heuristic tier pick. Default off. Editable via GET/PATCH /v1/daari/config ownership (config editor). |
| `routing.decision_classifier.model` | str | `'nimble'` | Decision model name proxied to Ollama /v1/systemone. Editable via config editor ownership. |
| `routing.decision_classifier.timeout_seconds` | float | `5.0` | Classifier request timeout; on timeout fall back to heuristics. Editable via config editor ownership. |
| `routing.decision_classifier.agent_turns` | bool | `False` | When true, also classify agent/tool turns. Default false (Ask only). Editable via config editor ownership. |
| `routing.session_affinity` | bool | `False` | When true, a tool-result continuation or an unchanged user-turn prefix reuses the session's prior tier instead of re-running rules. A new human turn re-routes. Default off. |
| `routing.session_affinity_ttl_seconds` | float | `1800.0` | How long a session pin (and the session cost-avoided rollup) is reused. 0 keeps the pin until process restart (in-process) or without a Redis TTL when cache.backend=redis. Ignored unless session_affinity is true. |
| `routing.classify_user_turn` | bool | `False` | When true, a tool-result continuation (no new user text) reuses the previous profile's category/complexity. Phase routing and stall escalation still inspect tool history. A new user message re-profiles. Default off. |
| `routing.classify_user_turn_agents` | bool | `True` | When classify_user_turn is false, still reuse profiles on tool-result continuations for agent User-Agents (cursor, claude-code, claude code, codex). Set false to disable the shortcut. Ignored when classify_user_turn is true (applies to every client). Default on. |
| `routing.harness_aware_profile` | bool | `True` | When true, complexity/category ignore system catalogs and recognized Codex/Claude Code harness blocks (system-reminder, environment_context, recommended_plugins, user_instructions, environments_instructions, agents.md envelope). prompt_tokens_est still counts the full request (#418, #541). Default on (no-op without those markers). |
| `routing.context_window_escalation` | bool | `True` | When true, pick a higher local tier before the first hop if the prompt estimate exceeds that tier's known context window (#385). |
| `routing.context_window_escalation_buffer` | float | `0.95` | Escalate when estimated tokens exceed window * buffer. |
| `routing.context_windows` | dict | `{'L3': 8192, 'L4': 32768, 'L5': 131072}` | Known context windows (tokens) per local tier. Missing = unknown, left alone. |
| `routing.shadow_sample_rate` | float | `0.0` | Fraction of local-tier responses replayed in the background at shadow_compare_tier to measure tier divergence. 0 disables. |
| `routing.shadow_compare_tier` | Literal | `''` | Tier to replay sampled requests at. Empty = highest configured local tier; L6 requires shadow_daily_usd > 0. |
| `routing.shadow_daily_usd` | float | `0.0` | Daily spend cap for L6 shadow replays. 0 forbids L6 shadow runs. |
| `routing.org_pool.enabled` | bool | `False` |  |
| `routing.org_pool.base_url` | str | `''` |  |
| `routing.org_pool.model` | str | `''` |  |
| `routing.org_pool.tier` | str | `'L5-org'` |  |
| `routing.local_pool.strategy` | str | `'least_outstanding'` | Host pick: least_outstanding or round_robin. Warm models still win ties. |
| `routing.local_pool.health_interval_seconds` | float | `15.0` | Background health-check interval. Requests use the last snapshot. |
| `routing.local_pool.frontier_fallback` | bool | `False` | When true and every local backend for the chosen tier is down or circuit-open, escalate to L6 instead of raising BackendUnavailable. Respects no_frontier, allowlists, budgets, and PII scrub. Default false so outages stay a hard 503 unless opted in (#846). |
| `routing.local_pool.backends` | list | `[]` |  |
| `frontier.enabled` | bool | `False` |  |
| `frontier.provider` | str | `'openai'` |  |
| `frontier.model` | str | `'gpt-4o-mini'` |  |
| `frontier.confidence_threshold` | float | `0.7` |  |
| `frontier.base_url` | str | `'https://api.openai.com/v1'` |  |
| `frontier.providers` | list | `[]` | Ordered L6 failover chain. Optional per-entry `timeout_s`, `retry_attempts`, and `retry_backoff_s` fall back to `upstream.frontier_timeout_seconds` / `upstream.retry` when unset. |
| `frontier.param_compat` | dict | `{}` | Per-model frontier parameter compatibility overrides. Merged over the builtin table (e.g. gpt-6-astra); empty keeps defaults. |
| `frontier.daily_budget_usd` | float | `0.0` |  |
| `frontier.monthly_budget_usd` | float | `0.0` |  |
| `frontier.soft_budget_ratio` | float | `0.8` |  |
| `frontier.scrub_pii` | bool | `False` |  |
| `frontier.price_per_1k_tokens` | float | `0.002` |  |
| `frontier.slim_prompts` | bool | `True` |  |
| `frontier.max_history_messages` | int | `8` |  |
| `frontier.prompt_cache` | bool | `True` |  |
| `frontier.compress_context` | bool | `False` |  |
| `frontier.compress_target_ratio` | float | `0.6` |  |
| `tools.unknown` | str | `'deny'` |  |
| `tools.allow` | list | `['git status', 'git diff', 'pytest', 'eslint *']` |  |
| `tools.block` | list | `['rm *', 'curl *\| sh', '*> /dev/*']` |  |
| `tools.timeout_seconds` | float | `30.0` |  |
| `context.enabled` | bool | `True` |  |
| `context.path` | str | `'~/.daari/context/commands'` |  |
| `usage.enabled` | bool | `True` |  |
| `usage.path` | str | `'~/.daari/usage/ledger.sqlite3'` |  |
| `usage.frontier_price_per_1k_tokens` | float | `0.002` | Flat fallback rate used to estimate what locally-served tokens would have cost on a frontier model. Applies only to models absent from `pricing.models`, and ignores input/output direction. |
| `usage.spend.enabled` | bool | `False` | Write one spend row per completed request (timestamp, key, team, tokens, cost, cost avoided). Off keeps the day ledger's write volume. |
| `usage.spend.path` | str | `'~/.daari/usage/spend.sqlite3'` | SQLite path for per-request spend rows. Ignored when observability.backend is postgres. |
| `files.enabled` | bool | `True` |  |
| `files.path` | str | `'~/.daari/files'` |  |
| `files.backend` | Literal | `'sqlite'` | sqlite (disk index + .bin files, default) or postgres (metadata + BYTEA content via observability.postgres_url) for multi-replica fleets (#465). |
| `files.max_bytes` | int | `104857600` | Maximum upload size in bytes for POST /v1/files. |
| `files.retention_days` | int | `0` | Fallback expiry for files without expires_after (#456). 0 keeps files forever until an explicit expires_after. |
| `files.max_total_bytes` | int | `0` | Hard cap on aggregate stored bytes (#456). 0 disables the cap. Uploads that would exceed it return 413. |
| `batches.enabled` | bool | `True` |  |
| `batches.path` | str | `'~/.daari/batches/jobs.sqlite3'` |  |
| `batches.backend` | Literal | `'sqlite'` | sqlite (default) or postgres (observability.postgres_url) so batch jobs are readable/cancellable across replicas (#465). |
| `batches.claim_ttl_seconds` | int | `90` | How long a replica's drain claim stays exclusive before another replica may reclaim a crashed worker (#465). Ignored for sqlite. |
| `batches.yield_to_interactive` | bool | `True` | When true, the batch worker waits while interactive HTTP requests are in flight before dispatching the next item (#444). |
| `batches.idle_poll_seconds` | float | `0.25` | How often to re-check interactive load while yielding. |
| `responses.backend` | Literal | `'sqlite'` | sqlite (default, path next to traces) or postgres (observability.postgres_url) so store:true / previous_response_id / background polling work across replicas (#481). |
| `responses.retention_days` | int | `0` | Delete stored responses older than this many days (#497). 0 keeps them forever. |
| `idempotency.enabled` | bool | `True` | When true, honor Idempotency-Key on chat completions and Responses. A missing header is always a no-op. |
| `idempotency.backend` | Literal | `'sqlite'` | sqlite (default, path next to traces) or postgres (observability.postgres_url) for multi-replica fleets. |
| `idempotency.ttl_seconds` | int | `86400` | How long completed idempotency records are kept (default 24h). |
| `idempotency.wait_seconds` | float | `60.0` | How long an in-flight duplicate waits for the first request. |
| `pricing.models` | dict | `{'gpt-4o': {'input_per_1m': 2.5, 'output_per_1m': 10.0, 'cached_input_per_1m': 1.25, 'cache_write_1h_per_1m': None, 'input_threshold_tokens'…` | Per-model, per-direction USD rates per 1M tokens. Keys match on longest prefix, so `gpt-4o` also prices `gpt-4o-2024-08-06` and a vendor prefix (`anthropic.claude-fable-5-1`) resolves the same way. Models absent here fall back to `usage.frontier_price_per_1k_tokens`; run `daari doctor` to list models being billed at the fallback rate. |
| `upstream.local_timeout_seconds` | float | `120.0` | Request timeout for local backends (Ollama, MLX). Generous because a large local model on a cold start can be genuinely slow. |
| `upstream.frontier_timeout_seconds` | float | `90.0` | Request timeout for frontier (L6) providers. Lower than local, since a hosted API that has not answered in 90s is usually not going to. |
| `upstream.request_deadline_seconds` | float | None | `None` | Optional wall-clock budget for one request across cache, local, and frontier hops. Each upstream call uses min(tier timeout, remaining). Unset or 0 keeps per-tier timeouts only. The X-Daari-Deadline-Ms header overrides this. |
| `upstream.retry.attempts` | int | `3` | Total attempts per upstream call, counting the first. `1` disables retries. Only transient failures are retried (408, 429, 5xx, connect and read timeouts); a 401 or malformed body fails immediately. |
| `upstream.retry.base_delay_ms` | int | `200` | First backoff, doubled per retry up to `max_delay_ms`. |
| `upstream.retry.max_delay_ms` | int | `5000` | Ceiling for a single backoff interval. |
| `upstream.retry.jitter` | float | `0.5` | Fraction of each backoff that is randomized, keeping the delay in [d*(1-jitter), d]. Spreads retries from requests that failed together instead of returning them in lockstep. |
| `upstream.pool_max_connections` | int | `100` | Max concurrent connections across the shared upstream httpx pool (Ollama, OpenAI-compat, MLX, frontier, embedder, TTS, ASR). |
| `upstream.pool_keepalive_connections` | int | `20` | Max idle keepalive connections retained in the shared upstream httpx pool. Cuts TCP/TLS handshake cost on repeated local hops. |
| `trace.enabled` | bool | `True` |  |
| `trace.path` | str | `'~/.daari/traces/traces.sqlite3'` |  |
| `trace.max_entries` | int | `200` |  |
| `observability.request_log_max_bytes` | int | `5242880` |  |
| `observability.request_log_backups` | int | `3` |  |
| `observability.prometheus` | bool | `True` |  |
| `observability.metrics_port` | int | `0` |  |
| `observability.otel` | bool | `False` |  |
| `observability.config_editor` | bool | `False` |  |
| `observability.backend` | Literal | `'sqlite'` |  |
| `observability.postgres_url` | str | `''` |  |
| `observability.postgres_pool_min` | int | `1` |  |
| `observability.postgres_pool_max` | int | `4` |  |
| `observability.structured_json_logs` | bool | `False` | Emit gateway request logs as single-line JSON to stdout (containers/SIEM). Default off. Editable via GET/PATCH /v1/daari/config ownership (config editor). |
| `observability.otlp_logs` | bool | `False` |  |
| `observability.stateless` | bool | `False` |  |
| `observability.retention.traces_days` | int | `0` |  |
| `observability.retention.ledger_days` | int | `0` |  |
| `observability.retention.audit_days` | int | `0` |  |
| `observability.retention.shadow_days` | int | `0` |  |
| `observability.retention.tasks_days` | int | `0` |  |
| `observability.retention.spend_days` | int | `0` | Delete per-request spend rows older than this many days (#709). 0 keeps them forever. |
| `observability.retention.request_log_days` | int | `0` | Delete gateway request-log lines and rotated backups older than this many days (#772). 0 keeps size-only rotation. |
| `observability.retention.batches_days` | int | `0` | Delete batch jobs older than this many days (#1136). 0 keeps them forever. |
| `observability.retention.cache_prune` | bool | `False` | When true, daari prune / daily sweep invoke L0 and L1 prune() using each cache's ttl_seconds (#1136). |
| `learning.enabled` | bool | `True` |  |
| `learning.path` | str | `'~/.daari/feedback/feedback.sqlite3'` |  |
| `learning.max_rows` | int | `20000` |  |
| `learning.auto_tune` | bool | `False` |  |
| `learning.tuner_min_samples` | int | `50` |  |
| `learning.capture_examples` | bool | `False` |  |
| `learning.examples_path` | str | `'~/.daari/training/examples.sqlite3'` |  |
| `learning.examples_max_rows` | int | `5000` |  |
| `learning.router_min_samples` | int | `200` |  |
| `learning.router_model_path` | str | `'~/.daari/learning/router-model.json'` |  |
| `learning.collective_enabled` | bool | `False` |  |
| `learning.collective_url` | str | `''` |  |
| `learning.collective_token` | str | `''` |  |
| `context_optimizer.enabled` | bool | `True` |  |
| `context_optimizer.max_history_messages` | int | `20` |  |
| `context_optimizer.squeeze_whitespace` | bool | `True` |  |
| `context_optimizer.compact` | bool | `False` |  |
| `guardrails.enabled` | bool | `False` |  |
| `guardrails.max_prompt_chars` | int | `0` |  |
| `guardrails.injection_action` | str | `'block'` |  |
| `guardrails.block_message` | str | `'Request blocked by daari guardrail.'` |  |
| `guardrails.input_rules` | list | `[]` |  |
| `guardrails.output_rules` | list | `[]` |  |
| `guardrails.stream_mode` | Literal | `'buffered'` | How output guardrails apply to SSE streams. buffered (default) scans the full answer before the first byte; incremental scans with a holdback window and keeps frontier relay eligible. |
| `guardrails.stream_holdback_chars` | int | `256` | Characters held back before emission in incremental stream_mode so a secret spanning two deltas is caught. Ignored when buffered. |
| `guardrails.scan_tool_results` | bool | `False` | When true, scan OpenAI role=tool and Anthropic tool_result message contents with output rules (secrets/PII/deny) before the model hop. System/user/assistant messages are unchanged. Default off. |
| `boundaries.enabled` | bool | `False` |  |
| `boundaries.mode` | Literal | `'block'` |  |
| `boundaries.product_name` | str | `''` |  |
| `boundaries.product_description` | str | `''` |  |
| `boundaries.allow_topics` | list | `[]` |  |
| `boundaries.deny_topics` | list | `[]` |  |
| `boundaries.examples_in` | list | `[]` |  |
| `boundaries.examples_out` | list | `[]` |  |
| `boundaries.refuse_message` | str | `'This assistant can only help with in-product questions.'` |  |
| `boundaries.clear_out_threshold` | float | `0.85` |  |
| `boundaries.clear_in_threshold` | float | `0.85` |  |
| `boundaries.local_judge_model` | str | None | `None` |  |
| `boundaries.quorum_votes` | int | `2` |  |
| `boundaries.frontier_judge_daily_budget_usd` | float | `0.5` |  |
| `boundaries.stages_b0` | bool | `True` |  |
| `boundaries.stages_b1` | bool | `True` |  |
| `boundaries.stages_b2` | bool | `True` |  |
| `boundaries.stages_b3` | bool | `False` |  |
| `boundaries.active_profile` | str | `''` |  |
| `boundaries.profiles` | dict | `{}` |  |
| `integrations.sourcegraph.url` | str | *(required)* |  |
| `integrations.sourcegraph.triggers` | list | `[]` |  |
| `integrations.ghe.url` | str | *(required)* |  |
| `integrations.ghe.triggers` | list | `[]` |  |
| `integrations.gitlab.url` | str | *(required)* |  |
| `integrations.gitlab.triggers` | list | `[]` |  |
| `integrations.mcp_servers` | list | `[]` | External MCP servers daari can call. Each entry: id, url, optional token/triggers. Opt-in OBO (#1319): auth_type=oauth2_token_exchange with token_exchange_endpoint, client_id, client_secret; optional audience, scopes, subject_token_type (default access_token). |
| `integrations.mcp_policy.allow` | list | `[]` | MCP tool names (glob) the caller may call. Empty = every tool not denied. |
| `integrations.mcp_policy.deny` | list | `[]` | MCP tool names (glob) the caller may never call. Deny beats allow. |
| `integrations.mcp_policy.servers.allow` | list | `[]` | MCP egress server ids (glob) the caller may reach. Empty = every server not denied. |
| `integrations.mcp_policy.servers.deny` | list | `[]` | MCP egress server ids (glob) the caller may never reach. Deny beats allow. |
| `integrations.mcp_policy.clients.allow` | list | `[]` | MCP client identities (glob) allowed to open the gateway. Empty = every client not denied. Match on clientInfo.name / OAuth client_id / User-Agent. |
| `integrations.mcp_policy.clients.deny` | list | `[]` | MCP client identities (glob) that may never open the gateway. Deny beats allow. |
| `integrations.mcp_policy.require_key_access_defined` | bool | `False` | When true, virtual keys with no MCP grant in metadata.mcp (allow / deny / servers.allow / servers.deny) fail initialize (HTTP 403 JSON-RPC -32003), get an empty tools/list, and tools/call deny on /mcp and /v1/mcp/query (#1352, #1389). Master key and flag-off behavior unchanged. Default false. Editable via GET/PATCH /v1/daari/config ownership (config editor). |
| `integrations.mcp_team_policies` | dict | `{}` | Per-team MCP tool policy keyed by team name; layered on mcp_policy. |
| `integrations.mcp_tasks.enabled` | bool | `True` |  |
| `integrations.mcp_tasks.long_running_tools` | list | `['route']` |  |
| `integrations.mcp_tasks.threshold_ms` | int | `0` |  |
| `integrations.mcp_tasks.path` | str | `'~/.daari/mcp-tasks'` |  |
| `integrations.mcp_tool_search.enabled` | bool | `False` | When true and the catalog exceeds min_catalog_size, rank tools by embedding similarity and return top_k. Default off — listing is unchanged. |
| `integrations.mcp_tool_search.min_catalog_size` | int | `40` | Catalogs at or under this size are returned unranked. |
| `integrations.mcp_tool_search.top_k` | int | `40` | Maximum tools returned after ranking. |
| `integrations.mcp_list_cache.ttl_ms` | int | `60000` | Client-hint TTL in milliseconds for tools/list _meta.ttlMs. 0 still emits the field; clients may treat it as uncacheable. |
| `integrations.mcp_egress.allow_private_networks` | bool | `False` | When true, MCP egress may POST to loopback, RFC1918, and link-local hosts (docker-compose / lab). Default false rejects those addresses after DNS resolution. |
| `integrations.mcp_egress.failure_threshold` | int | `3` | Consecutive MCP egress failures before the per-server circuit opens (#1203). Matches frontier `failure_threshold`. |
| `integrations.mcp_egress.cooldown_seconds` | float | `30.0` | Seconds an open MCP egress circuit stays fail-fast before a half-open probe (#1203). |
| `integrations.mcp_egress.server_side_responses` | bool | `False` | When true, Responses may include `type: mcp` tools that resolve to a configured `integrations.mcp_servers` id (`server_label`); daari lists tools, runs egress `tools/call` on model tool rounds, and continues the turn (#1232). Default false keeps the #1135 honesty 400 for hosted types. |
| `integrations.mcp_egress.server_side_messages` | bool | `False` | When true, Messages may include `mcp_servers` + `tools` entries with `type: mcp_toolset` whose `mcp_server_name` resolves to a configured `integrations.mcp_servers` id; daari lists tools, runs egress `tools/call` on model tool rounds, and continues the turn (#1261). Default false fails closed with an honesty 400. |
| `integrations.mcp_aggregate_egress.enabled` | bool | `False` | When true, `/mcp` `tools/list` includes tools from configured `integrations.mcp_servers`, namespaced as `{server_id}__{tool}`; `tools/call` on those names routes through the egress path (SSRF, breaker, guardrails, metering). Denied servers are omitted; per-server list failures degrade without emptying the catalog. Default false keeps the first-party-only catalog (#1294). Editable via GET/PATCH /v1/daari/config ownership (config editor). |
| `integrations.mcp_guardrails.enabled` | bool | `False` |  |
| `integrations.mcp_guardrails.max_prompt_chars` | int | `0` |  |
| `integrations.mcp_guardrails.injection_action` | str | `'block'` |  |
| `integrations.mcp_guardrails.block_message` | str | `'Request blocked by daari guardrail.'` |  |
| `integrations.mcp_guardrails.input_rules` | list | `[]` |  |
| `integrations.mcp_guardrails.output_rules` | list | `[]` |  |
| `integrations.mcp_guardrails.stream_mode` | Literal | `'buffered'` | How output guardrails apply to SSE streams. buffered (default) scans the full answer before the first byte; incremental scans with a holdback window and keeps frontier relay eligible. |
| `integrations.mcp_guardrails.stream_holdback_chars` | int | `256` | Characters held back before emission in incremental stream_mode so a secret spanning two deltas is caught. Ignored when buffered. |
| `integrations.mcp_guardrails.scan_tool_results` | bool | `False` | When true, scan OpenAI role=tool and Anthropic tool_result message contents with output rules (secrets/PII/deny) before the model hop. System/user/assistant messages are unchanged. Default off. |
| `integrations.mcp_oauth.protected_resource` | bool | `False` | When true, serve `GET /.well-known/oauth-protected-resource` (and the `/mcp`-scoped variant) and attach a `WWW-Authenticate` challenge on unauthenticated `/mcp` requests when API-key auth is on (#1262). Default false leaves the existing 401 body unchanged. Editable via GET/PATCH /v1/daari/config ownership (config editor); secrets stay non-editable. |
| `integrations.mcp_oauth.local_as` | bool | `False` | When true, expose a minimal on-box OAuth authorization server (``GET /.well-known/oauth-authorization-server`` + ``POST /oauth/token`` client_credentials) that mints short-lived Bearer tokens bound to an existing API/virtual key (#1293). Advertises the local issuer in ``authorization_servers`` when that list is empty. Default false — discovery-only / external IdP stays the ``protected_resource`` path. Editable via config editor ownership. |
| `integrations.mcp_oauth.resource` | str | `''` | Optional public base URL for the resource metadata `resource` field (defaults to the request base URL). Env: DAARI_INTEGRATIONS__MCP_OAUTH__RESOURCE. |
| `integrations.mcp_oauth.authorization_servers` | list | `[]` | Authorization server issuer URLs advertised in the metadata document. |
| `integrations.mcp_oauth.scopes_supported` | list | `['mcp']` | OAuth scopes advertised for the MCP resource. |
| `integrations.mcp_oauth.token_ttl_seconds` | int | `900` | Access-token lifetime in seconds for local AS mint (#1293). Default 900. |
| `integrations.mcp_oauth.signing_secret` | str | `''` | HS256 secret for minting MCP access tokens (#1293). Empty derives from the primary master key. Env: DAARI_INTEGRATIONS__MCP_OAUTH__SIGNING_SECRET. Not editable via the config editor (secrets stay redacted). |
| `integrations.mcp_openapi_proxy.enabled` | bool | `False` | When true, POST /mcp/proxy lists and calls tools derived from configured OpenAPI specs. Default false. |
| `integrations.mcp_openapi_proxy.specs` | list | `[]` | Allowlisted OpenAPI sources (id + openapi_url required). |
| `integrations.mcp_registry.enabled` | bool | `False` | When true, serve GET /v1/mcp/registry.json listing the built-in `/mcp` ingress and configured integrations.mcp_servers URLs. Advertisement-only; /mcp still enforces API-key / allowlists. Default false returns 404. Editable via config editor ownership. |
| `integrations.mcp_registry.public_base_url` | str | `''` | Optional public base URL for the built-in daari server entry (defaults to the request base URL). Env: DAARI_INTEGRATIONS__MCP_REGISTRY__PUBLIC_BASE_URL. |
| `enterprise.enabled` | bool | `False` |  |
| `enterprise.id` | str | None | `None` |  |
| `enterprise.org_id` | str | None | `None` |  |
| `enterprise.tenant_id` | str | None | `None` |  |
| `enterprise.control_plane_url` | str | None | `None` |  |
| `enterprise.org_token` | str | None | `None` |  |
| `enterprise.shared_cache_url` | str | None | `None` |  |
| `enterprise.shared_cache_token` | str | None | `None` |  |
| `enterprise.shared_cache_require_token` | bool | `False` |  |
| `enterprise.shared_cache_timeout_seconds` | float | `1.0` |  |
| `enterprise.shared_cache_max_retries` | int | `2` |  |
| `enterprise.shared_cache_backoff_seconds` | float | `0.2` |  |
| `enterprise.shared_cache_path` | str | None | `None` |  |
| `enterprise.learning_enabled` | bool | `False` |  |
| `enterprise.learning_url` | str | None | `None` |  |
| `enterprise.learning_token` | str | None | `None` |  |
| `enterprise.learning_timeout_seconds` | float | `0.5` |  |
| `enterprise.learning_sync_seconds` | float | `300.0` |  |
| `enterprise.learning_path` | str | None | `None` |  |
| `enterprise.policy_overrides` | dict | `{}` |  |
| `enterprise.profile` | str | `'developer'` |  |
| `enterprise.device_id` | str | None | `None` |  |
| `enterprise.config_signing_secret` | str | `''` |  |
| `enterprise.policy_sync_url` | str | None | `None` |  |
| `enterprise.cache.enabled` | bool | `False` |  |
| `enterprise.cache.share_classes` | list | `[]` |  |
| `enterprise.cache.no_org_cache_default` | bool | `False` |  |
| `enterprise.learning.enabled` | bool | `False` |  |
| `enterprise.learning.upload_prompts` | bool | `False` |  |
| `enterprise.learning.upload_code` | bool | `False` |  |
| `enterprise.sso.enabled` | bool | `False` |  |
| `enterprise.sso.issuer` | str | `'daari-dev'` |  |
| `enterprise.sso.secret` | str | `''` |  |
| `enterprise.sso.jwks_url` | str | `''` |  |
| `enterprise.sso.jwks_urls` | list | `[]` |  |
| `enterprise.sso.discovery_url` | str | `''` |  |
| `enterprise.sso.audience` | str | `''` |  |
| `enterprise.sso.role_claim` | str | `'role'` |  |
| `enterprise.sso.admin_min_role` | str | `'admin'` |  |
| `enterprise.sso.mint_virtual_key_on_login` | bool | `False` |  |
| `enterprise.sso.mapping_claim` | str | `'groups'` |  |
| `enterprise.sso.key_mappings` | dict | `{}` |  |
| `enterprise.sso.default_policy` | daari.enterprise.config.SsoKeyPolicy | None | `None` |  |
| `enterprise.sso.deny_unmapped` | bool | `False` |  |
| `enterprise.audit_path` | str | `'~/.daari/audit/audit.sqlite3'` |  |
| `enterprise.audit_backend` | Literal | `'sqlite'` | sqlite (default, per-node file) or postgres (observability.postgres_url) for a single fleet-wide hash chain (#483). |
| `alerts.budget_webhook_url` | str | `''` |  |
| `alerts.budget_webhook_secret` | str | `''` |  |
| `alerts.budget_thresholds` | list | `[0.8, 1.0]` |  |
| `skills_system_prefix` | str | `''` |  |
| `model_groups` | dict | `{}` | Named model groups (exact names or globs such as claude-*). Keys and teams reference them by name; enforcement is the union of allowed_models and the referenced groups, intersected across team and key. |

Per-key and per-team `rpd` (requests per UTC day, `0` = unlimited) is not a `rate_limit.*` setting. Set it on the key or team (`daari keys create/update --rpd`, `daari keys team-create/update --rpd`). See [auth and keys](../guides/configuration/auth-and-keys.md).

Per-key modality-family RPM/TPM (`chat` / `embeddings` / `images` / `audio` / `moderations` / `rerank` / `ocr` / `mcp` / `other`) is also not a `rate_limit.*` setting — store it on the virtual key as metadata `rate_families` (see auth-and-keys). Unset families keep global key rpm/tpm only (#1099).

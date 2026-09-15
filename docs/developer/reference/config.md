# Configuration reference

Generated from the pydantic settings model — do not edit by hand.

Keys live in `~/.daari/config.yaml` (nested YAML), can be overridden per-project
in `.daari.yaml`, and every key is also settable via environment variable:
`DAARI_<SECTION>__<KEY>` (double underscore per nesting level).

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `server.host` | str | `'127.0.0.1'` |  |
| `server.port` | int | `11435` |  |
| `server.api_key` | str | `''` |  |
| `server.virtual_keys.enabled` | bool | `True` |  |
| `server.virtual_keys.path` | str | `'~/.daari/auth/virtual-keys.sqlite3'` |  |
| `server.sse_keepalive_seconds` | float | `10.0` | Idle seconds before a streaming response emits a keepalive frame (SSE comment `: keepalive` on OpenAI/Anthropic/Responses routes, a blank line on the NDJSON Ollama facade). Keeps proxies and SDK read timeouts from dropping slow-to-first-token streams. 0 disables. |
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
| `ollama.base_url` | str | `'http://127.0.0.1:11434'` |  |
| `mlx.enabled` | bool | `False` |  |
| `mlx.base_url` | str | `'http://127.0.0.1:11440'` |  |
| `mlx.models` | dict | `{}` |  |
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
| `routing.learned_router` | bool | `False` |  |
| `routing.reasoning_effort_escalation` | bool | `False` |  |
| `routing.stall_escalation.enabled` | bool | `False` | When true, N identical tool calls in the last window, or N consecutive error tool results, escalate the chosen tier by one. Default off. |
| `routing.stall_escalation.repeats` | int | `3` | Identical calls or consecutive error results required to stall. |
| `routing.stall_escalation.window` | int | `6` | How many recent tool calls are inspected for identical repeats. |
| `routing.phase_routing.enabled` | bool | `False` | When true, the last window of tool-call names classifies the turn as explore / implement / verify and adjusts the heuristic tier. Default off. |
| `routing.phase_routing.window` | int | `6` | How many recent tool-call names are classified for phase. |
| `routing.phase_routing.explore` | int | str | `-1` | Tier adjustment for explore-phase turns. Default -1 (floor L3). |
| `routing.phase_routing.implement` | int | str | `0` | Tier adjustment for implement-phase turns. Default 0. |
| `routing.phase_routing.verify` | int | str | `0` | Tier adjustment for verify-phase turns. Default 0. |
| `routing.session_affinity` | bool | `False` | When true, a tool-result continuation or an unchanged user-turn prefix reuses the session's prior tier instead of re-running rules. A new human turn re-routes. Default off. |
| `routing.session_affinity_ttl_seconds` | float | `1800.0` | How long a session pin (and session cost-avoided rollup) is reused. With `cache.backend: redis`, also the Redis key TTL for fleet-shared pins/totals. 0 keeps the pin until process restart (in-process) or without Redis EX. Ignored unless session_affinity is true. |
| `routing.classify_user_turn` | bool | `False` | When true, a tool-result continuation (no new user text) reuses the previous profile's category/complexity. Phase routing and stall escalation still inspect tool history. A new user message re-profiles. Default off. |
| `routing.classify_user_turn_agents` | bool | `True` | When classify_user_turn is false, still reuse profiles on tool-result continuations for agent User-Agents (cursor, claude-code, claude code, codex). Set false to disable the shortcut. Ignored when classify_user_turn is true (applies to every client). Default on. |
| `routing.harness_aware_profile` | bool | `True` | When true, complexity/category ignore system catalogs and recognized Codex/Claude Code harness blocks. prompt_tokens_est still counts the full request (#418). Default on (no-op without those markers). |
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
| `routing.local_pool.backends` | list | `[]` |  |
| `frontier.enabled` | bool | `False` |  |
| `frontier.provider` | str | `'openai'` |  |
| `frontier.model` | str | `'gpt-4o-mini'` |  |
| `frontier.confidence_threshold` | float | `0.7` |  |
| `frontier.base_url` | str | `'https://api.openai.com/v1'` |  |
| `frontier.providers` | list | `[]` |  |
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
| `pricing.models` | dict | `{'gpt-4o': {'input_per_1m': 2.5, 'output_per_1m': 10.0, 'cached_input_per_1m': 1.25, 'cache_write_1h_per_1m': None, 'input_threshold_tokens'…` | Per-model, per-direction USD rates per 1M tokens. Keys match on longest prefix, so `gpt-4o` also prices `gpt-4o-2024-08-06` and a vendor prefix (`anthropic.claude-fable-5-1`) resolves the same way. Models absent here fall back to `usage.frontier_price_per_1k_tokens`; run `daari doctor` to list models being billed at the fallback rate. |
| `upstream.local_timeout_seconds` | float | `120.0` | Request timeout for local backends (Ollama, MLX). Generous because a large local model on a cold start can be genuinely slow. |
| `upstream.frontier_timeout_seconds` | float | `90.0` | Request timeout for frontier (L6) providers. Lower than local, since a hosted API that has not answered in 90s is usually not going to. |
| `upstream.retry.attempts` | int | `3` | Total attempts per upstream call, counting the first. `1` disables retries. Only transient failures are retried (408, 429, 5xx, connect and read timeouts); a 401 or malformed body fails immediately. |
| `upstream.retry.base_delay_ms` | int | `200` | First backoff, doubled per retry up to `max_delay_ms`. |
| `upstream.retry.max_delay_ms` | int | `5000` | Ceiling for a single backoff interval. |
| `upstream.retry.jitter` | float | `0.5` | Fraction of each backoff that is randomized, keeping the delay in [d*(1-jitter), d]. Spreads retries from requests that failed together instead of returning them in lockstep. |
| `trace.enabled` | bool | `True` |  |
| `trace.path` | str | `'~/.daari/traces/traces.sqlite3'` |  |
| `trace.max_entries` | int | `200` |  |
| `observability.request_log_max_bytes` | int | `5242880` |  |
| `observability.request_log_backups` | int | `3` |  |
| `observability.prometheus` | bool | `True` |  |
| `observability.otel` | bool | `False` |  |
| `observability.config_editor` | bool | `False` |  |
| `observability.backend` | Literal | `'sqlite'` |  |
| `observability.postgres_url` | str | `''` |  |
| `observability.structured_json_logs` | bool | `False` |  |
| `observability.stateless` | bool | `False` |  |
| `observability.retention.traces_days` | int | `0` |  |
| `observability.retention.ledger_days` | int | `0` |  |
| `observability.retention.audit_days` | int | `0` |  |
| `observability.retention.shadow_days` | int | `0` |  |
| `observability.retention.tasks_days` | int | `0` |  |
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
| `integrations.mcp_servers` | list | `[]` |  |
| `integrations.mcp_policy.allow` | list | `[]` | MCP tool names (glob) the caller may call. Empty = every tool not denied. |
| `integrations.mcp_policy.deny` | list | `[]` | MCP tool names (glob) the caller may never call. Deny beats allow. |
| `integrations.mcp_team_policies` | dict | `{}` | Per-team MCP tool policy keyed by team name; layered on mcp_policy. |
| `integrations.mcp_tasks.enabled` | bool | `True` |  |
| `integrations.mcp_tasks.long_running_tools` | list | `['route']` |  |
| `integrations.mcp_tasks.threshold_ms` | int | `0` |  |
| `integrations.mcp_tasks.path` | str | `'~/.daari/mcp-tasks'` |  |
| `integrations.mcp_tool_search.enabled` | bool | `False` | When true and the catalog exceeds min_catalog_size, rank tools by embedding similarity and return top_k. Default off — listing is unchanged. |
| `integrations.mcp_tool_search.min_catalog_size` | int | `40` | Catalogs at or under this size are returned unranked. |
| `integrations.mcp_tool_search.top_k` | int | `40` | Maximum tools returned after ranking. |
| `integrations.mcp_guardrails.enabled` | bool | `False` |  |
| `integrations.mcp_guardrails.max_prompt_chars` | int | `0` |  |
| `integrations.mcp_guardrails.injection_action` | str | `'block'` |  |
| `integrations.mcp_guardrails.block_message` | str | `'Request blocked by daari guardrail.'` |  |
| `integrations.mcp_guardrails.input_rules` | list | `[]` |  |
| `integrations.mcp_guardrails.output_rules` | list | `[]` |  |
| `integrations.mcp_guardrails.stream_mode` | Literal | `'buffered'` | How output guardrails apply to SSE streams. buffered (default) scans the full answer before the first byte; incremental scans with a holdback window and keeps frontier relay eligible. |
| `integrations.mcp_guardrails.stream_holdback_chars` | int | `256` | Characters held back before emission in incremental stream_mode so a secret spanning two deltas is caught. Ignored when buffered. |
| `integrations.mcp_guardrails.scan_tool_results` | bool | `False` | When true, scan OpenAI role=tool and Anthropic tool_result message contents with output rules (secrets/PII/deny) before the model hop. System/user/assistant messages are unchanged. Default off. |
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
| `alerts.budget_webhook_url` | str | `''` |  |
| `alerts.budget_thresholds` | list | `[0.8, 1.0]` |  |
| `skills_system_prefix` | str | `''` |  |

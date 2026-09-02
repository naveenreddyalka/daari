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
| `server.sse_keepalive_seconds` | float | `10.0` | Idle SSE keepalive interval while waiting for the first model chunk (0=off). |
| `rate_limit.rpm` | int | `0` | Default requests per minute per key (0=unlimited). |
| `rate_limit.tpm` | int | `0` | Default tokens per minute per key (0=unlimited). |
| `rate_limit.model_rpm` | int | `0` | Per-key-per-model RPM. 0 falls back to rpm. |
| `rate_limit.model_tpm` | int | `0` | Per-key-per-model TPM. 0 falls back to tpm. |
| `rate_limit.max_in_flight` | int | `0` | Global in-flight request cap. 0 disables the concurrency gate. |
| `rate_limit.queue_size` | int | `32` | Waiters allowed when in-flight is full; overflow is 503 + Retry-After. |
| `rate_limit.retry_after_seconds` | int | `1` | Retry-After value on 429/503. |
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
| `routing.prefer` | Literal | `'balanced'` |  |
| `routing.confidence_threshold` | float | `0.7` |  |
| `routing.category_policies` | dict | `{}` |  |
| `routing.max_tier_for_chat` | Optional | `None` |  |
| `routing.latency_budget_ms` | int | `0` |  |
| `routing.warm_model_preference` | bool | `True` |  |
| `routing.learned_router` | bool | `False` |  |
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
| `pricing.models` | dict | `{'gpt-4o': {'input_per_1m': 2.5, 'output_per_1m': 10.0, 'cached_input_per_1m': 1.25}, 'gpt-4o-mini': {'input_per_1m': 0.15, 'output_per_1m':…` | Per-model, per-direction USD rates per 1M tokens. Keys match on longest prefix, so `gpt-4o` also prices `gpt-4o-2024-08-06`. Models absent here fall back to `usage.frontier_price_per_1k_tokens`; run `daari doctor` to list models being billed at the fallback rate. |
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
| `skills_system_prefix` | str | `''` |  |

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
| `models.l3` | str | `'llama3.2:3b'` |  |
| `models.l4` | str | `'llama3.1:8b'` |  |
| `models.l5` | str | `'llama3.1:70b'` |  |
| `models.weights` | dict | `{}` |  |
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
| `cache.l1.shadow_sample_rate` | float | `0.05` |  |
| `routing.prefer` | str | `'balanced'` |  |
| `routing.confidence_threshold` | float | `0.7` |  |
| `routing.category_policies` | dict | `{}` |  |
| `routing.max_tier_for_chat` | str | None | `None` |  |
| `routing.latency_budget_ms` | int | `0` |  |
| `routing.warm_model_preference` | bool | `True` |  |
| `routing.learned_router` | bool | `False` |  |
| `frontier.enabled` | bool | `False` |  |
| `frontier.provider` | str | `'openai'` |  |
| `frontier.model` | str | `'gpt-4o-mini'` |  |
| `frontier.confidence_threshold` | float | `0.7` |  |
| `frontier.base_url` | str | `'https://api.openai.com/v1'` |  |
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
| `tools.block` | list | `['rm *', 'curl *| sh', '*> /dev/*']` |  |
| `tools.timeout_seconds` | float | `30.0` |  |
| `context.enabled` | bool | `True` |  |
| `context.path` | str | `'~/.daari/context/commands'` |  |
| `usage.enabled` | bool | `True` |  |
| `usage.path` | str | `'~/.daari/usage/ledger.sqlite3'` |  |
| `usage.frontier_price_per_1k_tokens` | float | `0.002` |  |
| `trace.enabled` | bool | `True` |  |
| `trace.path` | str | `'~/.daari/traces/traces.sqlite3'` |  |
| `trace.max_entries` | int | `200` |  |
| `observability.request_log_max_bytes` | int | `5242880` |  |
| `observability.request_log_backups` | int | `3` |  |
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
| `integrations.sourcegraph.url` | str | *(required)* |  |
| `integrations.sourcegraph.triggers` | list | `[]` |  |
| `integrations.ghe.url` | str | *(required)* |  |
| `integrations.ghe.triggers` | list | `[]` |  |
| `integrations.gitlab.url` | str | *(required)* |  |
| `integrations.gitlab.triggers` | list | `[]` |  |
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
| `enterprise.cache.enabled` | bool | `False` |  |
| `enterprise.cache.share_classes` | list | `[]` |  |
| `enterprise.cache.no_org_cache_default` | bool | `False` |  |
| `enterprise.learning.enabled` | bool | `False` |  |
| `enterprise.learning.upload_prompts` | bool | `False` |  |
| `enterprise.learning.upload_code` | bool | `False` |  |
| `skills_system_prefix` | str | `''` |  |

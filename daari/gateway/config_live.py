"""Apply the safe config subset to a live AppContext.

Shared by `PATCH /v1/daari/config` (live-tune) and `POST /v1/daari/reload-config`
(#1234) so both paths mutate the same router/engine handles the same way.
"""

from __future__ import annotations

from typing import Any

from daari.config.validate import ConfigValidationError


def apply_live_config(
    ctx: Any,
    *,
    app_state: Any = None,
    routing: dict[str, Any] | None = None,
    frontier: dict[str, Any] | None = None,
    cache: dict[str, Any] | None = None,
    integrations: dict[str, Any] | None = None,
    observability: dict[str, Any] | None = None,
    guardrails: dict[str, Any] | None = None,
    decisions: dict[str, Any] | None = None,
    systemone: dict[str, Any] | None = None,
    security: dict[str, Any] | None = None,
    new_boundaries: Any = None,
) -> None:
    """Mutate `ctx.settings` and the router in place; inputs are pre-validated.

    Raises ConfigValidationError for `integrations.mcp_servers` ids that are not
    configured live (ceilings merge only; a new server needs a restart).
    """
    routing = routing or {}
    frontier = frontier or {}
    cache = cache or {}
    integrations = integrations or {}
    observability = observability or {}
    guardrails = guardrails or {}
    decisions = decisions or {}
    systemone = systemone or {}
    security = security or {}

    if "confidence_threshold" in routing:
        ctx.router.confidence_threshold = routing["confidence_threshold"]
        ctx.settings.routing.confidence_threshold = routing["confidence_threshold"]
    if "latency_budget_ms" in routing:
        ctx.router.latency_budget_ms = routing["latency_budget_ms"]
        ctx.settings.routing.latency_budget_ms = routing["latency_budget_ms"]
    if "max_tier_for_chat" in routing:
        ctx.router.max_tier_for_chat = routing["max_tier_for_chat"]
        ctx.settings.routing.max_tier_for_chat = routing["max_tier_for_chat"]
    if "prefer" in routing:
        ctx.router.model_preference = routing["prefer"]
        ctx.settings.routing.prefer = routing["prefer"]
    classifier = routing.get("decision_classifier") or {}
    if "enabled" in classifier:
        ctx.settings.routing.decision_classifier.enabled = classifier["enabled"]
        ctx.router.decision_classifier_enabled = classifier["enabled"]
    if "model" in classifier:
        ctx.settings.routing.decision_classifier.model = classifier["model"]
        ctx.router.decision_classifier_model = classifier["model"]
    if "timeout_seconds" in classifier:
        ctx.settings.routing.decision_classifier.timeout_seconds = classifier["timeout_seconds"]
        ctx.router.decision_classifier_timeout_seconds = classifier["timeout_seconds"]
    if "agent_turns" in classifier:
        ctx.settings.routing.decision_classifier.agent_turns = classifier["agent_turns"]
        ctx.router.decision_classifier_agent_turns = classifier["agent_turns"]
    compact = routing.get("compact_to_fit") or {}
    if "enabled" in compact:
        ctx.settings.routing.compact_to_fit.enabled = compact["enabled"]
        ctx.router.compact_to_fit_enabled = compact["enabled"]
    if "max_messages" in compact:
        ctx.settings.routing.compact_to_fit.max_messages = compact["max_messages"]
        ctx.router.compact_to_fit_max_messages = compact["max_messages"]
    if "max_tokens" in compact:
        ctx.settings.routing.compact_to_fit.max_tokens = compact["max_tokens"]
        ctx.router.compact_to_fit_max_tokens = compact["max_tokens"]
    if "signal_overrides" in routing:
        from daari.config.settings import SignalOverrideRule

        rules = [SignalOverrideRule.model_validate(row) for row in routing["signal_overrides"]]
        ctx.settings.routing.signal_overrides = rules
        ctx.router.signal_overrides = list(rules)
    if "virtual_models" in routing:
        mapping = {
            str(name): [str(c) for c in (candidates or [])]
            for name, candidates in dict(routing["virtual_models"] or {}).items()
        }
        ctx.settings.routing.virtual_models = mapping
        ctx.router.virtual_models = dict(mapping)
    if "virtual_model_latency_slo_ms" in routing:
        slo_map = {
            str(name): float(ms)
            for name, ms in dict(routing["virtual_model_latency_slo_ms"] or {}).items()
        }
        ctx.settings.routing.virtual_model_latency_slo_ms = slo_map
        ctx.router.virtual_model_latency_slo_ms = dict(slo_map)
    if "baggage_to_tags" in routing:
        ctx.settings.routing.baggage_to_tags = bool(routing["baggage_to_tags"])
    for key in ("daily_budget_usd", "monthly_budget_usd", "soft_budget_ratio"):
        if key in frontier:
            setattr(ctx.settings.frontier, key, frontier[key])
            if hasattr(ctx.router, f"frontier_{key}"):
                setattr(ctx.router, f"frontier_{key}", frontier[key])
    if "l0_ttl_seconds" in cache:
        ctx.settings.cache.l0.ttl_seconds = cache["l0_ttl_seconds"]
    if "l1_ttl_seconds" in cache:
        ctx.settings.cache.l1.ttl_seconds = cache["l1_ttl_seconds"]
    if "l1_similarity_threshold" in cache:
        ctx.settings.cache.l1.similarity_threshold = cache["l1_similarity_threshold"]
        ctx.router.semantic_cache.similarity_threshold = cache["l1_similarity_threshold"]
    mcp_oauth = integrations.get("mcp_oauth") or {}
    for key in ("local_as", "protected_resource"):
        if key in mcp_oauth:
            setattr(ctx.settings.integrations.mcp_oauth, key, mcp_oauth[key])
    mcp_agg = integrations.get("mcp_aggregate_egress") or {}
    if "enabled" in mcp_agg:
        ctx.settings.integrations.mcp_aggregate_egress.enabled = mcp_agg["enabled"]
    mcp_reg = integrations.get("mcp_registry") or {}
    if "enabled" in mcp_reg:
        ctx.settings.integrations.mcp_registry.enabled = mcp_reg["enabled"]
    mcp_policy = integrations.get("mcp_policy") or {}
    if "require_key_access_defined" in mcp_policy:
        ctx.settings.integrations.mcp_policy.require_key_access_defined = mcp_policy[
            "require_key_access_defined"
        ]
    if "mcp_servers" in integrations:
        ceilings = {str(row["id"]): row for row in integrations["mcp_servers"] if "id" in row}
        known = {s.id for s in ctx.settings.integrations.mcp_servers}
        unknown = sorted(set(ceilings) - known)
        if unknown:
            raise ConfigValidationError(
                f"mcp_servers unknown ids (ceilings merge only): {unknown}"
            )
        for server in ctx.settings.integrations.mcp_servers:
            row = ceilings.get(server.id)
            if row is None:
                continue
            if "rpm" in row:
                server.rpm = row["rpm"]
            if "tpm" in row:
                server.tpm = row["tpm"]
    if "structured_json_logs" in observability:
        ctx.settings.observability.structured_json_logs = observability["structured_json_logs"]
        from daari.gateway.request_log import configure_request_log

        configure_request_log(structured_json_logs=observability["structured_json_logs"])
    if "team_metrics" in observability:
        enabled = bool(observability["team_metrics"])
        ctx.settings.observability.team_metrics = enabled
        metrics = getattr(ctx, "metrics", None)
        if metrics is not None:
            if enabled:
                from daari.observability.metrics import sync_team_metrics_allowlist

                metrics.configure_team_metrics(enabled=True, allowed=frozenset())
                store = getattr(app_state, "virtual_key_store", None) if app_state else None
                if store is None:
                    store = getattr(ctx, "virtual_key_store", None)
                sync_team_metrics_allowlist(metrics, store)
            else:
                metrics.configure_team_metrics(enabled=False, allowed=frozenset())
    if "otel_include_request_tags" in observability:
        enabled = bool(observability["otel_include_request_tags"])
        ctx.settings.observability.otel_include_request_tags = enabled
        router = getattr(ctx, "router", None)
        if router is not None:
            router.otel_include_request_tags = enabled
    if "log_blocked_content" in guardrails:
        enabled = bool(guardrails["log_blocked_content"])
        ctx.settings.guardrails.log_blocked_content = enabled
        engine = getattr(getattr(ctx, "router", None), "guardrails", None)
        if engine is not None:
            engine.log_blocked_content = enabled
    if "local_models" in decisions:
        ctx.settings.decisions.local_models = list(decisions["local_models"])
    if "base_url" in systemone:
        ctx.settings.systemone.base_url = systemone["base_url"]
        ctx.router.systemone_base_url = systemone["base_url"]
    if security:
        if "offline_mode" in security:
            ctx.settings.security.offline_mode = security["offline_mode"]
        if "offline_allow_hosts" in security:
            ctx.settings.security.offline_allow_hosts = list(security["offline_allow_hosts"])
        from daari.security.offline_mode import configure_offline_mode_from_settings

        configure_offline_mode_from_settings(ctx.settings)
    if new_boundaries is not None:
        from daari.gateway.boundaries import (
            copy_runtime_hooks,
            default_local_judge,
            engine_from_settings,
        )

        prev = ctx.router.boundaries
        ctx.settings.boundaries = new_boundaries
        ctx.router.boundaries = engine_from_settings(ctx.settings, judge=default_local_judge)
        copy_runtime_hooks(ctx.router.boundaries, prev)

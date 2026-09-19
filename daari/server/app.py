from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from daari.auth.rate_limit import (
    RATELIMIT_WARNING_HEADER,
    RateLimiter,
    build_rate_limiter,
    estimate_audio_upload_tokens,
    estimate_request_tokens,
    request_model,
)
from daari.auth.postgres_virtual_keys import virtual_key_store_from_settings
from daari.auth.virtual_keys import VirtualKeyStore
from daari.config.settings import Settings
from daari.gateway.anthropic import AnthropicGatewayAdapter
from daari.gateway.mcp import MCPGatewayAdapter
from daari.gateway.ollama_compat import OllamaCompatGatewayAdapter
from daari.gateway.openai import create_gateway_router
from daari.gateway.request_log import configure_request_log
from daari.gateway.responses import ResponsesGatewayAdapter
from daari.router.router import AppContext
from daari.server.auth import extract_api_key, resolve_auth


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.load()
    # Issue #288: resolve secret:// config values once, before anything can
    # read them. A failed ref is fatal — the daemon must not start half-keyed.
    from daari.security.secret_refs import resolve_settings_secrets

    resolve_settings_secrets(resolved)
    configure_request_log(
        max_bytes=resolved.observability.request_log_max_bytes,
        backups=resolved.observability.request_log_backups,
        structured_json_logs=resolved.observability.structured_json_logs,
    )
    vk_store: VirtualKeyStore | None = None
    if resolved.server.virtual_keys.enabled:
        vk_store = virtual_key_store_from_settings(resolved)  # type: ignore[assignment]

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = AppContext.from_settings(resolved)
        app.state.ctx.virtual_key_store = vk_store
        from daari.gateway.boundaries import startup_warnings
        from daari.gateway.request_log import log_gateway_event

        for warning in startup_warnings(resolved):
            log_gateway_event("startup_warning", {"message": warning})
        app.state.ctx.start_org_learning_sync()
        app.state.ctx.start_backend_health()
        app.state.ctx.start_retention_sweep()
        from daari.enterprise.postgres_audit import audit_log_from_settings
        from daari.observability.budget_alerts import BudgetAlerter

        cache = resolved.cache
        redis_url = ""
        redis_timeout = 2.0
        if getattr(cache, "backend", "disk") == "redis":
            redis_url = getattr(cache, "redis_url", "") or ""
            redis_timeout = float(getattr(cache, "redis_timeout_seconds", 2.0) or 2.0)
        app.state.budget_alerter = BudgetAlerter(
            webhook_url=resolved.alerts.budget_webhook_url,
            thresholds=tuple(resolved.alerts.budget_thresholds),
            webhook_secret=resolved.alerts.budget_webhook_secret,
            audit=audit_log_from_settings(resolved),
            metrics=app.state.ctx.metrics,
            redis_url=redis_url,
            redis_timeout_seconds=redis_timeout,
        )
        # Wire interactive load probe, then resume unfinished batches (#443/#444).
        batch_store = getattr(app.state.ctx, "batch_store", None)
        limiter = getattr(app.state, "rate_limiter", None)
        if batch_store is not None and limiter is not None:
            batch_store.idle_probe = limiter.interactive_load
        if batch_store is not None:

            def _make_execute(job_id: str):
                async def execute_one(item_body: dict) -> dict:
                    from daari.gateway.openai import _execute_batch_chat_body

                    job = batch_store.get(job_id)
                    gov = job.governance if job is not None else None
                    return await _execute_batch_chat_body(app.state.ctx, item_body, governance=gov)

                return execute_one

            batch_store.resume_incomplete_with(_make_execute)
        metrics_stop = None
        obs = resolved.observability
        metrics_port = int(getattr(obs, "metrics_port", 0) or 0)
        if obs.prometheus and metrics_port > 0:
            from daari.gateway.request_log import log_gateway_event
            from daari.observability.metrics_listen import start_metrics_listener

            bound, metrics_stop = await start_metrics_listener(
                app, host="127.0.0.1", port=metrics_port
            )
            log_gateway_event(
                "metrics_listener",
                {"host": "127.0.0.1", "port": bound},
            )
            app.state.metrics_listen_port = bound
        try:
            yield
        finally:
            if metrics_stop is not None:
                await metrics_stop()
            await app.state.ctx.stop_backend_health()
            await app.state.ctx.stop_org_learning_sync()
            await app.state.ctx.stop_retention_sweep()

    app = FastAPI(title="daari", version="0.1.0", lifespan=lifespan)
    app.state.virtual_key_store = vk_store
    app.state.rate_limiter = build_rate_limiter(resolved)

    if resolved.observability.otel:

        @app.middleware("http")
        async def otel_trace_context(request: Request, call_next):
            """Extract inbound W3C traceparent for parenting + outbound inject (#485)."""
            from daari.observability.otel import (
                extract_inbound_context,
                reset_inbound_context,
            )

            token = extract_inbound_context(request.headers)
            try:
                return await call_next(request)
            finally:
                reset_inbound_context(token)

    master_keys = resolved.server.master_keys()
    if len(master_keys) > 1:
        from daari.enterprise.postgres_audit import audit_log_from_settings

        audit_log_from_settings(resolved).record(
            actor="daari",
            role="system",
            action="auth.master_key_overlap",
            detail={"count": len(master_keys)},
        )
    # Auth middleware runs when a master key is set OR virtual keys exist /
    # are enabled (so newly created keys are enforced without restart... we
    # check the store on each request).
    auth_active = bool(master_keys) or resolved.server.virtual_keys.enabled
    if auth_active:
        # Probes stay open: orchestrators can't attach API keys (issue #105).
        # /metrics follows server.api_key (F3): open only when master unset
        # AND no virtual-key enforcement required — keep previous behavior:
        # when master_key set, /metrics needs auth; when only VK store, open.
        open_paths = {"/health", "/ready", "/v1/messages/health"}
        if not master_keys:
            open_paths.add("/metrics")

        @app.middleware("http")
        async def require_api_key(request: Request, call_next):
            if request.url.path in open_paths:
                return await call_next(request)
            # When no master key and the VK store is empty, stay open so
            # local single-user installs aren't suddenly locked out.
            store: VirtualKeyStore | None = getattr(request.app.state, "virtual_key_store", None)
            has_virtual = bool(store and store.enabled and store.list())
            if not master_keys and not has_virtual:
                return await call_next(request)

            supplied = extract_api_key(request.headers)
            claims = resolve_auth(supplied, master_key=master_keys, store=store)
            if claims is None and resolved.enterprise.sso.enabled and supplied:
                # Allow verified OIDC/HMAC SSO bearers through; endpoints still
                # enforce role via _require_admin_role (issue #136).
                try:
                    from daari.enterprise.sso import verify_access_token

                    sso_claims = verify_access_token(supplied, resolved.enterprise.sso)
                    request.state.sso_claims = sso_claims
                    return await call_next(request)
                except Exception:
                    pass
            if claims is not None and claims.kind == "expired":
                from daari.enterprise.postgres_audit import audit_log_from_settings

                expires_at = (
                    claims.virtual_key.expires_at if claims.virtual_key is not None else None
                )
                audit_log_from_settings(resolved).record(
                    actor=claims.client_id or claims.key_id or "unknown",
                    role="key",
                    action="auth.key_expired",
                    detail={"key_id": claims.key_id, "expires_at": expires_at},
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "type": "authentication_error",
                            "code": "key_expired",
                            "message": "Virtual API key has expired.",
                        }
                    },
                )
            if claims is None:
                from daari.enterprise.audit import record_invalid_key
                from daari.enterprise.postgres_audit import audit_log_from_settings

                record_invalid_key(
                    audit_log_from_settings(resolved),
                    supplied=supplied,
                    path=request.url.path,
                )
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "type": "authentication_error",
                            "message": "Invalid or missing daari API key.",
                        }
                    },
                )
            budget_response_headers: dict[str, str] = {}
            ledger = None
            statuses: list = []
            team = None
            team_ids: list = []
            client = ""
            pricing = None
            fallback = 0.002
            if claims.kind == "virtual" and claims.virtual_key is not None and store is not None:
                # Per-key frontier budget, charged to the key that caused the
                # spend. Billing against global spend let one key exhaust every
                # other key's allowance (#158). The global cap still applies
                # separately as an outer ceiling in the router.
                ctx = getattr(request.app.state, "ctx", None)
                ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
                if ledger is not None and getattr(ledger, "enabled", False):
                    from daari.auth.budgets import (
                        budget_error,
                        budget_status,
                        tightest_request_window,
                        tightest_window,
                    )
                    from daari.gateway.budget_headers import (
                        BUDGET_WARNING_HEADER,
                        QUOTA_REQUESTS_LIMIT_HEADER,
                        QUOTA_REQUESTS_REMAINING_HEADER,
                        QUOTA_REQUESTS_WARNING_HEADER,
                        budget_headers,
                        retry_after_seconds,
                    )

                    client = claims.client_id or claims.key_id or ""
                    pricing = getattr(resolved, "pricing", None)
                    fallback = float(resolved.usage.frontier_price_per_1k_tokens or 0.002)
                    key = claims.virtual_key
                    team = store.get_team(key.team_id) if key is not None else None
                    team_ids = store.team_client_ids(team.team_id) if team is not None else []
                    statuses = budget_status(
                        key,
                        team,
                        ledger,
                        client_id=client,
                        team_client_ids=team_ids,
                        pricing=pricing,
                        fallback_per_1k=fallback,
                    )
                    exceeded = next((status for status in statuses if status.exceeded), None)
                    if exceeded is not None:
                        # #319: the 402 carries the same budget headers as a 2xx
                        # (remaining 0) plus Retry-After from the window reset.
                        headers = budget_headers(exceeded)
                        headers["Retry-After"] = str(retry_after_seconds(exceeded))
                        err_kwargs: dict = {
                            "client_id": client,
                            "window": exceeded.window,
                            "spend": exceeded.spend,
                            "scope": exceeded.scope,
                        }
                        if exceeded.quota == "requests":
                            err_kwargs["quota"] = "requests"
                            err_kwargs["spend_requests"] = int(exceeded.spend)
                            err_kwargs["limit_requests"] = int(exceeded.limit)
                        metrics = getattr(getattr(request.app.state, "ctx", None), "metrics", None)
                        if metrics is not None and hasattr(metrics, "record_reject"):
                            kind = "request_quota" if exceeded.quota == "requests" else "budget"
                            metrics.record_reject(kind)
                        return JSONResponse(
                            status_code=402,
                            content={"error": budget_error(**err_kwargs)},
                            headers=headers,
                        )
                    soft_ratio = float(getattr(resolved.frontier, "soft_budget_ratio", 0.8) or 0.0)
                    tightest = tightest_window(statuses)
                    if tightest is not None:
                        usd_soft = tightest.in_soft_band(soft_ratio)
                        budget_response_headers = budget_headers(tightest, soft=usd_soft)
                        if usd_soft:
                            request.state.budget_soft = True
                    request_tightest = tightest_request_window(statuses)
                    if request_tightest is not None:
                        # Keep USD window/scope headers when both quotas apply.
                        budget_response_headers[QUOTA_REQUESTS_REMAINING_HEADER] = str(
                            int(request_tightest.remaining)
                        )
                        budget_response_headers[QUOTA_REQUESTS_LIMIT_HEADER] = str(
                            int(request_tightest.limit)
                        )
                        if tightest is None:
                            budget_response_headers.update(budget_headers(request_tightest))
                        if request_tightest.in_soft_band(soft_ratio):
                            budget_response_headers[QUOTA_REQUESTS_WARNING_HEADER] = "soft"
                            request.state.request_quota_soft = True
            request.state.auth_claims = claims
            response = await call_next(request)
            if budget_response_headers and 200 <= response.status_code < 300:
                for header, value in budget_response_headers.items():
                    response.headers.setdefault(header, value)
                metrics = getattr(getattr(request.app.state, "ctx", None), "metrics", None)
                if (
                    budget_response_headers.get(QUOTA_REQUESTS_WARNING_HEADER) == "soft"
                    and metrics is not None
                    and hasattr(metrics, "record_soft_warning")
                ):
                    metrics.record_soft_warning("request_quota")
                elif (
                    budget_response_headers.get(BUDGET_WARNING_HEADER) == "soft"
                    and metrics is not None
                    and hasattr(metrics, "record_soft_warning")
                ):
                    metrics.record_soft_warning("budget")
            alerter = getattr(request.app.state, "budget_alerter", None)
            if (
                alerter is not None
                and getattr(alerter, "enabled", False)
                and claims.kind == "virtual"
                and claims.virtual_key is not None
                and store is not None
                and ledger is not None
            ):
                after = budget_status(
                    claims.virtual_key,
                    team,
                    ledger,
                    client_id=client,
                    team_client_ids=team_ids,
                    pricing=pricing,
                    fallback_per_1k=fallback,
                )
                import asyncio

                asyncio.create_task(
                    asyncio.to_thread(
                        alerter.notify,
                        statuses,
                        after,
                        key=claims.virtual_key,
                        team=team,
                    )
                )
            return response

    open_rate_paths = {"/health", "/ready", "/v1/messages/health", "/metrics", "/v1/daari/stats"}
    # Batch/files admin traffic must not look like interactive load (#444).
    non_interactive_prefixes = ("/v1/batches", "/v1/files")

    @app.middleware("http")
    async def enforce_rate_limits(request: Request, call_next):
        if request.url.path in open_rate_paths:
            return await call_next(request)
        limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
        if limiter is None:
            return await call_next(request)

        raw = await request.body()
        payload: dict = {}
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                payload = {}
        model = request_model(payload)
        tokens = estimate_request_tokens(payload)
        if request.url.path == "/v1/audio/transcriptions":
            audio_tokens = estimate_audio_upload_tokens(
                raw, request.headers.get("content-type", "")
            )
            if audio_tokens is not None:
                tokens = audio_tokens
        claims = getattr(request.state, "auth_claims", None)
        if claims is None:
            store = getattr(request.app.state, "virtual_key_store", None)
            claims = resolve_auth(
                extract_api_key(request.headers),
                master_key=master_keys,
                store=store,
            )
        virtual = getattr(claims, "virtual_key", None) if claims is not None else None
        key_id = (getattr(claims, "key_id", None) if claims is not None else None) or (
            "master" if getattr(claims, "kind", None) == "master" else "anonymous"
        )
        rpm = int(getattr(virtual, "rpm", 0) or 0) or None
        tpm = int(getattr(virtual, "tpm", 0) or 0) or None
        rpd = int(getattr(virtual, "rpd", 0) or 0) or None
        team_id = getattr(virtual, "team_id", None) if virtual is not None else None
        team_rpm = None
        team_tpm = None
        team_rpd = None
        if team_id:
            store = getattr(request.app.state, "virtual_key_store", None)
            team = (
                store.get_team(team_id)
                if store is not None and hasattr(store, "get_team")
                else None
            )
            if team is not None:
                team_rpm = int(getattr(team, "rpm", 0) or 0) or None
                team_tpm = int(getattr(team, "tpm", 0) or 0) or None
                team_rpd = int(getattr(team, "rpd", 0) or 0) or None
        decision = limiter.check(
            key_id=key_id,
            model=model,
            tokens=tokens,
            rpm=rpm,
            tpm=tpm,
            team_id=team_id,
            team_rpm=team_rpm,
            team_tpm=team_tpm,
            rpd=rpd,
            team_rpd=team_rpd,
        )
        if not decision.allowed:
            metrics = getattr(getattr(request.app.state, "ctx", None), "metrics", None)
            if metrics is not None and hasattr(metrics, "record_reject"):
                metrics.record_reject("rate_limit")
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "type": "rate_limit_error",
                        "message": f"{decision.scope or 'rate'} limit exceeded.",
                    }
                },
                headers=decision.headers(),
            )

        soft_ratio = 0.8
        ctx = getattr(request.app.state, "ctx", None)
        settings = getattr(ctx, "settings", None) if ctx is not None else None
        if settings is not None:
            soft_ratio = float(
                getattr(getattr(settings, "frontier", None), "soft_budget_ratio", 0.8) or 0.0
            )
        rate_soft = decision.in_soft_band(soft_ratio)
        if rate_soft:
            request.state.rate_limit_soft = True

        slot = await limiter.acquire()
        if not slot.allowed:
            headers = slot.headers()
            headers.setdefault("Retry-After", str(limiter.retry_after_seconds))
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "type": "rate_limit_error",
                        "message": "In-flight concurrency limit exceeded.",
                    }
                },
                headers=headers,
            )
        path = request.url.path
        track_interactive = not path.startswith(non_interactive_prefixes)
        if track_interactive:
            limiter.begin_interactive()
        try:
            response = await call_next(request)
        finally:
            if track_interactive:
                limiter.end_interactive()
            await limiter.release()
        soft_headers = decision.headers(soft=rate_soft)
        for header, value in soft_headers.items():
            response.headers.setdefault(header, value)
        if soft_headers.get(RATELIMIT_WARNING_HEADER) == "soft":
            metrics = getattr(getattr(request.app.state, "ctx", None), "metrics", None)
            if metrics is not None and hasattr(metrics, "record_soft_warning"):
                metrics.record_soft_warning("rate_limit")
        return response

    app.include_router(create_gateway_router())
    app.include_router(AnthropicGatewayAdapter().router())
    app.include_router(MCPGatewayAdapter().router())
    app.include_router(OllamaCompatGatewayAdapter().router())
    app.include_router(ResponsesGatewayAdapter().router())
    return app

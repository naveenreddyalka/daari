from __future__ import annotations

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from daari.auth.rate_limit import (
    RateLimiter,
    build_rate_limiter,
    estimate_request_tokens,
    request_model,
)
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
        vk_store = VirtualKeyStore(
            resolved.virtual_keys_path, enabled=resolved.server.virtual_keys.enabled
        )

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
        from daari.enterprise.audit import AuditLog
        from daari.observability.budget_alerts import BudgetAlerter

        app.state.budget_alerter = BudgetAlerter(
            webhook_url=resolved.alerts.budget_webhook_url,
            thresholds=tuple(resolved.alerts.budget_thresholds),
            audit=AuditLog(resolved.enterprise.audit_path),
            metrics=app.state.ctx.metrics,
        )
        try:
            yield
        finally:
            await app.state.ctx.stop_backend_health()
            await app.state.ctx.stop_org_learning_sync()

    app = FastAPI(title="daari", version="0.1.0", lifespan=lifespan)
    app.state.virtual_key_store = vk_store
    app.state.rate_limiter = build_rate_limiter(resolved)

    master_key = resolved.server.api_key.strip()
    # Auth middleware runs when a master key is set OR virtual keys exist /
    # are enabled (so newly created keys are enforced without restart... we
    # check the store on each request).
    auth_active = bool(master_key) or resolved.server.virtual_keys.enabled
    if auth_active:
        # Probes stay open: orchestrators can't attach API keys (issue #105).
        # /metrics follows server.api_key (F3): open only when master unset
        # AND no virtual-key enforcement required — keep previous behavior:
        # when master_key set, /metrics needs auth; when only VK store, open.
        open_paths = {"/health", "/ready", "/v1/messages/health"}
        if not master_key:
            open_paths.add("/metrics")

        @app.middleware("http")
        async def require_api_key(request: Request, call_next):
            if request.url.path in open_paths:
                return await call_next(request)
            # When no master key and the VK store is empty, stay open so
            # local single-user installs aren't suddenly locked out.
            store: VirtualKeyStore | None = getattr(request.app.state, "virtual_key_store", None)
            has_virtual = bool(store and store.enabled and store.list())
            if not master_key and not has_virtual:
                return await call_next(request)

            supplied = extract_api_key(request.headers)
            claims = resolve_auth(supplied, master_key=master_key, store=store)
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
                from daari.enterprise.audit import AuditLog

                expires_at = (
                    claims.virtual_key.expires_at if claims.virtual_key is not None else None
                )
                AuditLog(resolved.enterprise.audit_path).record(
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
                    from daari.auth.budgets import budget_error, budget_status, tightest_window
                    from daari.gateway.budget_headers import budget_headers, retry_after_seconds

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
                        return JSONResponse(
                            status_code=402,
                            content={
                                "error": budget_error(
                                    client_id=client,
                                    window=exceeded.window,
                                    spend=exceeded.spend,
                                    scope=exceeded.scope,
                                )
                            },
                            headers=headers,
                        )
                    tightest = tightest_window(statuses)
                    if tightest is not None:
                        budget_response_headers = budget_headers(tightest)
            request.state.auth_claims = claims
            response = await call_next(request)
            if budget_response_headers and 200 <= response.status_code < 300:
                for header, value in budget_response_headers.items():
                    response.headers.setdefault(header, value)
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

    open_rate_paths = {"/health", "/ready", "/v1/messages/health", "/metrics"}

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
        claims = getattr(request.state, "auth_claims", None)
        if claims is None:
            store = getattr(request.app.state, "virtual_key_store", None)
            claims = resolve_auth(
                extract_api_key(request.headers),
                master_key=master_key,
                store=store,
            )
        virtual = getattr(claims, "virtual_key", None) if claims is not None else None
        key_id = (getattr(claims, "key_id", None) if claims is not None else None) or (
            "master" if getattr(claims, "kind", None) == "master" else "anonymous"
        )
        rpm = int(getattr(virtual, "rpm", 0) or 0) or None
        tpm = int(getattr(virtual, "tpm", 0) or 0) or None
        decision = limiter.check(
            key_id=key_id,
            model=model,
            tokens=tokens,
            rpm=rpm,
            tpm=tpm,
        )
        if not decision.allowed:
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
        try:
            response = await call_next(request)
        finally:
            await limiter.release()
        for header, value in decision.headers().items():
            response.headers.setdefault(header, value)
        return response

    app.include_router(create_gateway_router())
    app.include_router(AnthropicGatewayAdapter().router())
    app.include_router(MCPGatewayAdapter().router())
    app.include_router(OllamaCompatGatewayAdapter().router())
    app.include_router(ResponsesGatewayAdapter().router())
    return app

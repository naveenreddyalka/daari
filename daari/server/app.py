from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
    configure_request_log(
        max_bytes=resolved.observability.request_log_max_bytes,
        backups=resolved.observability.request_log_backups,
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
        app.state.ctx.start_org_learning_sync()
        try:
            yield
        finally:
            await app.state.ctx.stop_org_learning_sync()

    app = FastAPI(title="daari", version="0.1.0", lifespan=lifespan)
    app.state.virtual_key_store = vk_store

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
            if claims.kind == "virtual" and claims.virtual_key is not None and store is not None:
                if not store.check_rpm(claims.virtual_key):
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": {
                                "type": "rate_limit_error",
                                "message": f"Virtual key RPM limit ({claims.virtual_key.rpm}) exceeded.",
                            }
                        },
                    )
                # Per-key frontier budget against the usage ledger.
                ctx = getattr(request.app.state, "ctx", None)
                ledger = getattr(getattr(ctx, "router", None), "usage_ledger", None)
                price = float(resolved.frontier.price_per_1k_tokens or 0.002)
                if ledger is not None and getattr(ledger, "enabled", False):
                    client = claims.client_id or claims.key_id or ""
                    if claims.daily_budget_usd > 0:
                        # Approximate: ledger is not yet per-client frontier-only
                        # for a single day helper — use client report if present,
                        # else fall back to global frontier spend (conservative).
                        spend = float(ledger.frontier_spend_usd(price_per_1k_tokens=price))
                        if spend >= claims.daily_budget_usd:
                            return JSONResponse(
                                status_code=402,
                                content={
                                    "error": {
                                        "type": "budget_exceeded",
                                        "message": (
                                            f"Virtual key daily budget "
                                            f"(${claims.daily_budget_usd:.4f}) exceeded."
                                        ),
                                        "client_id": client,
                                    }
                                },
                            )
            request.state.auth_claims = claims
            return await call_next(request)

    app.include_router(create_gateway_router())
    app.include_router(AnthropicGatewayAdapter().router())
    app.include_router(MCPGatewayAdapter().router())
    app.include_router(OllamaCompatGatewayAdapter().router())
    app.include_router(ResponsesGatewayAdapter().router())
    return app

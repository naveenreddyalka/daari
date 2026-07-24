from __future__ import annotations

import hmac
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from daari.config.settings import Settings
from daari.gateway.anthropic import AnthropicGatewayAdapter
from daari.gateway.mcp import MCPGatewayAdapter
from daari.gateway.ollama_compat import OllamaCompatGatewayAdapter
from daari.gateway.openai import create_gateway_router
from daari.gateway.request_log import configure_request_log
from daari.gateway.responses import ResponsesGatewayAdapter
from daari.router.router import AppContext


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.load()
    configure_request_log(
        max_bytes=resolved.observability.request_log_max_bytes,
        backups=resolved.observability.request_log_backups,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = AppContext.from_settings(resolved)
        app.state.ctx.start_org_learning_sync()
        try:
            yield
        finally:
            await app.state.ctx.stop_org_learning_sync()

    app = FastAPI(title="daari", version="0.1.0", lifespan=lifespan)

    api_key = resolved.server.api_key.strip()
    if api_key:
        # Probes stay open: orchestrators can't attach API keys (issue #105).
        open_paths = {"/health", "/ready", "/v1/messages/health"}

        @app.middleware("http")
        async def require_api_key(request: Request, call_next):
            if request.url.path in open_paths:
                return await call_next(request)
            supplied = request.headers.get("x-api-key", "")
            if not supplied:
                authorization = request.headers.get("authorization", "")
                if authorization.lower().startswith("bearer "):
                    supplied = authorization[len("bearer ") :].strip()
            if not hmac.compare_digest(supplied, api_key):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "type": "authentication_error",
                            "message": "Invalid or missing daari API key.",
                        }
                    },
                )
            return await call_next(request)

    app.include_router(create_gateway_router())
    app.include_router(AnthropicGatewayAdapter().router())
    app.include_router(MCPGatewayAdapter().router())
    app.include_router(OllamaCompatGatewayAdapter().router())
    app.include_router(ResponsesGatewayAdapter().router())
    return app

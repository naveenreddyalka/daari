from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from daari.config.settings import Settings
from daari.gateway.openai import create_gateway_router
from daari.router.router import AppContext


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or Settings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.ctx = AppContext.from_settings(resolved)
        yield

    app = FastAPI(title="daari", version="0.1.0", lifespan=lifespan)
    app.include_router(create_gateway_router())
    return app

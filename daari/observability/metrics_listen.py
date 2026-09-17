"""Optional scrape-only Prometheus HTTP listener (#594)."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse, Response


def prometheus_text_for_app(app: FastAPI) -> str | None:
    """Same exposition as GET /metrics on the main app, or None when disabled."""
    from daari.observability.prometheus import render_prometheus

    ctx = getattr(app.state, "ctx", None)
    if ctx is None:
        return None
    settings = ctx.settings
    if not settings.observability.prometheus:
        return None

    budget_state: dict[str, Any] | None = None
    false_hit_rate: float | None = None
    price = float(settings.frontier.price_per_1k_tokens or 0.002)
    ledger = getattr(ctx.router, "usage_ledger", None)
    if ledger is not None and getattr(ledger, "enabled", False):
        try:
            daily = float(ledger.frontier_spend_usd(price_per_1k_tokens=price))
            monthly = float(ledger.frontier_spend_usd_month(price_per_1k_tokens=price))
            daily_cap = float(settings.frontier.daily_budget_usd or 0.0)
            monthly_cap = float(settings.frontier.monthly_budget_usd or 0.0)
            state = "ok"
            soft = settings.frontier.soft_budget_ratio
            for spend, cap in ((daily, daily_cap), (monthly, monthly_cap)):
                if cap <= 0:
                    continue
                ratio = spend / cap
                if ratio >= 1.0:
                    state = "exceeded"
                    break
                if ratio >= soft and state == "ok":
                    state = "soft"
            budget_state = {
                "daily_spend_usd": daily,
                "monthly_spend_usd": monthly,
                "daily_budget_usd": daily_cap,
                "monthly_budget_usd": monthly_cap,
                "state": state,
            }
        except Exception:
            budget_state = None
    feedback = getattr(ctx.router, "feedback_store", None)
    if feedback is not None and getattr(feedback, "enabled", False):
        try:
            shadow = feedback.shadow_stats(days=7)
            samples = sum(row.get("samples", 0) for row in shadow.values())
            disagrees = sum(row.get("disagreements", 0) for row in shadow.values())
            if samples:
                false_hit_rate = round(disagrees / samples, 4)
        except Exception:
            false_hit_rate = None

    limiter = getattr(app.state, "rate_limiter", None)
    rate_limit = limiter.snapshot() if limiter is not None else None
    pool = getattr(ctx, "local_pool", None) or getattr(ctx.router, "local_pool", None)
    backend_pool = pool.snapshot() if pool is not None else None
    team_budgets: list[dict[str, Any]] | None = None
    store = getattr(app.state, "virtual_key_store", None) or getattr(ctx, "virtual_key_store", None)
    if store is not None and ledger is not None and getattr(ledger, "enabled", False):
        try:
            from daari.auth.budgets import collect_team_budget_gauges

            rows = collect_team_budget_gauges(
                store, ledger, fallback_per_1k=price
            )
            team_budgets = rows or None
        except Exception:
            team_budgets = None
    return render_prometheus(
        ctx.metrics,
        budget_state=budget_state,
        false_hit_rate=false_hit_rate,
        rate_limit=rate_limit,
        backend_pool=backend_pool,
        team_budgets=team_budgets,
    )


def create_metrics_app(main_app: FastAPI) -> FastAPI:
    """Auth-free FastAPI that only serves GET /metrics from ``main_app`` state."""
    metrics_app = FastAPI(title="daari-metrics", docs_url=None, redoc_url=None)

    @metrics_app.get("/metrics")
    async def metrics() -> Response:
        body = prometheus_text_for_app(main_app)
        if body is None:
            return Response(status_code=404, content="prometheus metrics disabled")
        return PlainTextResponse(
            content=body,
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    return metrics_app


async def start_metrics_listener(
    main_app: FastAPI,
    *,
    host: str = "127.0.0.1",
    port: int,
) -> tuple[int, Callable[[], Awaitable[None]]]:
    """Bind a scrape-only uvicorn server; ``port=0`` picks an ephemeral port."""
    import uvicorn

    config = uvicorn.Config(
        create_metrics_app(main_app),
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="off",
    )
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        if task.done():
            await task
            raise RuntimeError("metrics listener failed to start")
        await asyncio.sleep(0.01)

    bound = port
    for srv in getattr(server, "servers", []) or []:
        for sock in getattr(srv, "sockets", []) or []:
            bound = int(sock.getsockname()[1])
            break
        if bound:
            break

    async def stop() -> None:
        server.should_exit = True
        await task

    return bound, stop

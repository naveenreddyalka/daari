"""App-level graceful shutdown / drain (#1104)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.rate_limit import MemoryCounterBackend, RateLimiter
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app
from daari.server.shutdown import (
    BUDGET_ALERT_DRAIN_TIMEOUT_SECONDS,
    await_budget_alert_tasks,
    begin_shutdown,
    track_budget_alert_task,
)


def _app(settings):
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    return application


@pytest.mark.asyncio
async def test_ready_503_shutting_down_while_health_ok(settings, monkeypatch):
    app = _app(settings)

    async def backend_ok(probe_url: str, timeout: float = 2.0) -> str:
        return "ok"

    monkeypatch.setattr("daari.gateway.openai.check_model_backend", backend_ok)
    begin_shutdown(app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        ready = await client.get("/ready")
        health = await client.get("/health")
    assert ready.status_code == 503
    assert ready.json() == {"status": "shutting_down"}
    assert health.status_code == 200
    assert health.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_acquire_rejects_new_arrivals_when_draining():
    limiter = RateLimiter(
        MemoryCounterBackend(), max_in_flight=2, queue_size=8, retry_after_seconds=3
    )
    first = await limiter.acquire()
    assert first.allowed
    limiter.begin_drain()
    denied = await limiter.acquire()
    assert not denied.allowed
    assert denied.retry_after == 3
    assert denied.scope == "concurrency"
    await limiter.release()


@pytest.mark.asyncio
async def test_queued_waiter_completes_after_drain_starts():
    limiter = RateLimiter(
        MemoryCounterBackend(), max_in_flight=1, queue_size=8, retry_after_seconds=1
    )
    holder = await limiter.acquire()
    assert holder.allowed

    async def wait_for_slot() -> bool:
        slot = await limiter.acquire()
        return slot.allowed

    waiter = asyncio.create_task(wait_for_slot())
    await asyncio.sleep(0.05)
    assert limiter.queued == 1
    limiter.begin_drain()
    new_arrival = await limiter.acquire()
    assert not new_arrival.allowed
    await limiter.release()
    assert await asyncio.wait_for(waiter, timeout=1.0) is True
    await limiter.release()


@pytest.mark.asyncio
async def test_drain_rejects_even_when_concurrency_gate_disabled():
    limiter = RateLimiter(MemoryCounterBackend(), max_in_flight=0, retry_after_seconds=2)
    limiter.begin_drain()
    denied = await limiter.acquire()
    assert not denied.allowed
    assert denied.retry_after == 2


@pytest.mark.asyncio
async def test_await_budget_alert_tasks_bounded(settings):
    app = _app(settings)
    started = asyncio.Event()
    finished = asyncio.Event()

    async def slow() -> None:
        started.set()
        await asyncio.sleep(10)
        finished.set()

    track_budget_alert_task(app, asyncio.create_task(slow()))
    await started.wait()
    await await_budget_alert_tasks(app, timeout=0.05)
    assert not finished.is_set()
    # Cancel leftover so the event loop stays clean.
    for task in list(getattr(app.state, "budget_alert_tasks", set())):
        task.cancel()
    await asyncio.sleep(0)


def test_graceful_timeout_default_on_settings(settings):
    assert settings.server.graceful_timeout_seconds == 30.0
    assert BUDGET_ALERT_DRAIN_TIMEOUT_SECONDS > 0


def test_serve_exposes_graceful_timeout_option():
    from typer.main import get_command

    from daari.cli.app import app as cli

    command = get_command(cli)
    serve = command.commands["serve"]
    opts = {param.name for param in serve.params}
    assert "graceful_timeout" in opts


@pytest.mark.asyncio
async def test_middleware_returns_503_on_new_request_during_shutdown(settings, monkeypatch):
    settings.rate_limit.max_in_flight = 4
    app = _app(settings)

    async def fake_execute(request: InternalRequest) -> InternalResponse:
        return InternalResponse(
            content="ok",
            model="llama3.2:3b",
            daari_meta=DaariMeta(
                tier="L3",
                executor="ollama",
                provider_id="ollama",
                latency_ms=1,
            ),
        )

    monkeypatch.setattr(app.state.ctx.router.ollama, "execute", fake_execute)
    begin_shutdown(app)
    payload = {"model": "daari", "messages": [{"role": "user", "content": "hi"}]}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/chat/completions", json=payload)
    assert response.status_code == 503
    assert response.headers.get("retry-after")
    assert response.json()["error"]["type"] == "rate_limit_error"

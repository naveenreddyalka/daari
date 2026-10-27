"""HTTP poll resolves orphaned background Responses jobs (#1957)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from daari.gateway.response_store import ResponseStore
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.mark.asyncio
async def test_poll_expired_lease_resolves_failed(settings, monkeypatch):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    store = ResponseStore(Path(settings.trace.path).expanduser().parent / "responses.sqlite3")
    rid = "resp_fleet_orphan"
    store.put(
        rid,
        {
            "id": rid,
            "object": "response",
            "status": "in_progress",
            "model": "daari",
            "output": [],
        },
        job_owner="replica-dead",
        lease_expires_at=int(time.time()) - 30,
    )
    logged: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.responses.log_gateway_event",
        lambda name, fields=None: logged.append(name),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(f"/v1/responses/{rid}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error"]["code"] == "orphan_reclaimed"
    assert "orphan" in body["error"]["message"].lower()
    assert store.get(rid)["status"] == "failed"
    assert "responses.job_lease_reclaimed" in logged

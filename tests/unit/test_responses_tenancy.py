"""Responses API owner checks for GET and previous_response_id (#453)."""

from __future__ import annotations

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse
from daari.router.router import AppContext
from daari.server.app import create_app


def _app_with_keys(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.trace.path = str(tmp_path / "trace.jsonl")
    store = VirtualKeyStore(settings.virtual_keys_path)
    alice = store.create("alice", client_id="alice")
    bob = store.create("bob", client_id="bob")
    application = create_app(settings)
    application.state.ctx = AppContext.from_settings(settings)
    application.state.virtual_key_store = store
    application.state.ctx.virtual_key_store = store

    async def fake_route(request: InternalRequest) -> InternalResponse:
        last = request.messages[-1].content if request.messages else ""
        return InternalResponse(
            content=f"echo:{last}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    application.state.ctx.router.route = fake_route
    return application, alice, bob


@pytest.mark.asyncio
async def test_get_response_404_for_other_key(settings, tmp_path):
    app, alice, bob = _app_with_keys(settings, tmp_path)
    alice_h = {"Authorization": f"Bearer {alice.plaintext}"}
    bob_h = {"Authorization": f"Bearer {bob.plaintext}"}
    master_h = {"Authorization": "Bearer master"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses", json={"model": "daari", "input": "secret"}, headers=alice_h
        )
        assert created.status_code == 200
        rid = created.json()["id"]
        assert (await client.get(f"/v1/responses/{rid}", headers=alice_h)).status_code == 200
        assert (await client.get(f"/v1/responses/{rid}", headers=bob_h)).status_code == 404
        assert (await client.get(f"/v1/responses/{rid}", headers=master_h)).status_code == 200
        missing = await client.get("/v1/responses/resp_missing", headers=bob_h)
        assert missing.status_code == 404
        assert missing.json()["detail"] == "response not found"


@pytest.mark.asyncio
async def test_previous_response_id_rejects_cross_tenant(settings, tmp_path):
    app, alice, bob = _app_with_keys(settings, tmp_path)
    alice_h = {"Authorization": f"Bearer {alice.plaintext}"}
    bob_h = {"Authorization": f"Bearer {bob.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses", json={"model": "daari", "input": "hello"}, headers=alice_h
        )
        rid = first.json()["id"]
        denied = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "steal", "previous_response_id": rid},
            headers=bob_h,
        )
        assert denied.status_code == 400
        assert "previous_response_id not found" in denied.json()["detail"]
        ok = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "and then?", "previous_response_id": rid},
            headers=alice_h,
        )
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_background_poll_uses_create_time_owner(settings, tmp_path):
    app, alice, bob = _app_with_keys(settings, tmp_path)
    alice_h = {"Authorization": f"Bearer {alice.plaintext}"}
    bob_h = {"Authorization": f"Bearer {bob.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "later", "background": True},
            headers=alice_h,
        )
        assert created.json()["status"] == "queued"
        rid = created.json()["id"]
        body = None
        for _ in range(40):
            fetched = await client.get(f"/v1/responses/{rid}", headers=alice_h)
            assert fetched.status_code == 200
            body = fetched.json()
            if body.get("status") == "completed":
                break
            await asyncio.sleep(0.02)
        assert body is not None and body["status"] == "completed"
        assert (await client.get(f"/v1/responses/{rid}", headers=bob_h)).status_code == 404


@pytest.mark.asyncio
async def test_cancel_and_delete_honor_get_tenancy(settings, tmp_path):
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    app, alice, bob = _app_with_keys(settings, tmp_path)
    alice_h = {"Authorization": f"Bearer {alice.plaintext}"}
    bob_h = {"Authorization": f"Bearer {bob.plaintext}"}
    master_h = {"Authorization": "Bearer master"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses", json={"model": "daari", "input": "keep"}, headers=alice_h
        )
        rid = created.json()["id"]
        assert created.json()["status"] == "completed"

        bob_cancel = await client.post(f"/v1/responses/{rid}/cancel", headers=bob_h)
        assert bob_cancel.status_code == 404
        bob_delete = await client.delete(f"/v1/responses/{rid}", headers=bob_h)
        assert bob_delete.status_code == 404
        assert (await client.get(f"/v1/responses/{rid}", headers=alice_h)).status_code == 200

        cancel = await client.post(f"/v1/responses/{rid}/cancel", headers=alice_h)
        assert cancel.status_code == 200
        assert cancel.json()["id"] == rid
        assert cancel.json()["status"] == "completed"

        again = await client.post(f"/v1/responses/{rid}/cancel", headers=alice_h)
        assert again.status_code == 200
        assert again.json()["status"] == "completed"

        missing = await client.post("/v1/responses/resp_missing/cancel", headers=alice_h)
        assert missing.status_code == 404

        master_delete = await client.delete(f"/v1/responses/{rid}", headers=master_h)
        assert master_delete.status_code == 200
        assert master_delete.json()["deleted"] is True
        assert (await client.get(f"/v1/responses/{rid}", headers=alice_h)).status_code == 404
        assert (await client.get(f"/v1/responses/{rid}", headers=master_h)).status_code == 404
        assert (await client.delete(f"/v1/responses/{rid}", headers=alice_h)).status_code == 404

        chained = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "next", "previous_response_id": rid},
            headers=alice_h,
        )
        assert chained.status_code == 400
        assert "previous_response_id not found" in chained.json()["detail"]

    from daari.enterprise.audit import AuditLog

    rows = AuditLog(settings.enterprise.audit_path).list(action="tenancy.denied")
    kinds = {row["detail"]["kind"] for row in rows}
    ids = {row["detail"]["id"] for row in rows}
    assert "response" in kinds
    assert rid in ids
    assert all("keep" not in str(row) for row in rows)


@pytest.mark.asyncio
async def test_cancel_stops_in_flight_background_job(settings, tmp_path):
    app, alice, _bob = _app_with_keys(settings, tmp_path)
    started = asyncio.Event()

    async def slow_route(request: InternalRequest) -> InternalResponse:
        started.set()
        await asyncio.sleep(0.15)
        last = request.messages[-1].content if request.messages else ""
        return InternalResponse(
            content=f"late:{last}",
            model="llama3.2:3b",
            daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
        )

    app.state.ctx.router.route = slow_route
    alice_h = {"Authorization": f"Bearer {alice.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "slow", "background": True},
            headers=alice_h,
        )
        assert created.json()["status"] == "queued"
        rid = created.json()["id"]
        await asyncio.wait_for(started.wait(), timeout=1)
        cancelled = await client.post(f"/v1/responses/{rid}/cancel", headers=alice_h)
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        await asyncio.sleep(0.25)
        fetched = await client.get(f"/v1/responses/{rid}", headers=alice_h)
        assert fetched.status_code == 200
        assert fetched.json()["status"] == "cancelled"
        assert fetched.json().get("output") == []

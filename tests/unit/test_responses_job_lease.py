"""Background Responses job lease / in_progress reclaim (#1957)."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from daari.config.settings import Settings
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.gateway.postgres_responses import PostgresResponseStore
from daari.gateway.response_store import ResponseStore
from daari.gateway.responses import (
    LEASE_TTL_SECONDS,
    ResponsesGatewayAdapter,
    _reclaim_expired_job,
)
from daari.router.router import AppContext
from daari.server.app import create_app


def test_sqlite_migrates_job_owner_and_lease_columns(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE responses ("
            "response_id TEXT PRIMARY KEY, body TEXT NOT NULL, "
            "conversation TEXT NOT NULL, stored INTEGER NOT NULL, "
            "owner_key_id TEXT, created_at INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO responses VALUES (?, ?, ?, 1, ?, ?)",
            ("resp_old", '{"id":"resp_old","status":"queued"}', "[]", "vk", 1),
        )
    store = ResponseStore(path)
    store.put(
        "resp_old",
        {"id": "resp_old", "status": "in_progress"},
        job_owner="pod-a",
        lease_expires_at=1_700_000_000,
    )
    got = store.get("resp_old")
    assert got is not None
    assert got["_job_owner"] == "pod-a"
    assert got["_lease_expires_at"] == 1_700_000_000


def test_sqlite_put_preserves_lease_when_omitted(tmp_path):
    store = ResponseStore(tmp_path / "r.sqlite3")
    store.put(
        "resp_x",
        {"id": "resp_x", "status": "queued"},
        job_owner="pod-1",
        lease_expires_at=100,
    )
    store.put("resp_x", {"id": "resp_x", "status": "in_progress"})
    got = store.get("resp_x")
    assert got["_job_owner"] == "pod-1"
    assert got["_lease_expires_at"] == 100


def test_postgres_memory_lease_roundtrip():
    dsn = f"memory:lease-{uuid.uuid4().hex}"
    a = PostgresResponseStore(dsn)
    b = PostgresResponseStore(dsn)
    a.put(
        "resp_pg",
        {"id": "resp_pg", "status": "queued"},
        job_owner="pod-b",
        lease_expires_at=999,
    )
    got = b.get("resp_pg")
    assert got is not None
    assert got["_job_owner"] == "pod-b"
    assert got["_lease_expires_at"] == 999
    b.put("resp_pg", {"id": "resp_pg", "status": "in_progress"})
    assert a.get("resp_pg")["_job_owner"] == "pod-b"
    assert a.get("resp_pg")["_lease_expires_at"] == 999


def test_reclaim_expired_persists_failed_and_logs(tmp_path, monkeypatch):
    store = ResponseStore(tmp_path / "r.sqlite3")
    store.put(
        "resp_orphan",
        {"id": "resp_orphan", "object": "response", "status": "in_progress", "output": []},
        job_owner="dead-pod",
        lease_expires_at=int(time.time()) - 60,
    )
    events: list[tuple[str, dict]] = []

    def capture(name: str, fields: dict | None = None) -> None:
        events.append((name, dict(fields or {})))

    monkeypatch.setattr("daari.gateway.responses.log_gateway_event", capture)
    body = _reclaim_expired_job(store, "resp_orphan", store.get("resp_orphan"))
    assert body is not None
    assert body["status"] == "failed"
    assert "orphan" in body["error"]["message"].lower()
    persisted = store.get("resp_orphan")
    assert persisted is not None
    assert persisted["status"] == "failed"
    assert any(name == "responses.job_lease_reclaimed" for name, _ in events)


def test_reclaim_skips_fresh_lease(tmp_path):
    store = ResponseStore(tmp_path / "r.sqlite3")
    store.put(
        "resp_live",
        {"id": "resp_live", "status": "in_progress", "output": []},
        job_owner="pod-live",
        lease_expires_at=int(time.time()) + LEASE_TTL_SECONDS,
    )
    assert _reclaim_expired_job(store, "resp_live", store.get("resp_live")) is None
    assert store.get("resp_live")["status"] == "in_progress"


@pytest.mark.asyncio
async def test_run_background_marks_in_progress_and_renews_lease(tmp_path, monkeypatch):
    store = ResponseStore(tmp_path / "r.sqlite3")
    store.put(
        "resp_bg",
        {"id": "resp_bg", "object": "response", "status": "queued", "output": []},
        job_owner="pod-old",
        lease_expires_at=1,
    )
    seen_statuses: list[str] = []
    gate = asyncio.Event()

    class Ctx:
        settings = Settings()

        class router:
            @staticmethod
            async def route(internal):
                current = store.get("resp_bg")
                assert current is not None
                seen_statuses.append(current["status"])
                assert current["status"] == "in_progress"
                assert current["_job_owner"]
                assert int(current["_lease_expires_at"] or 0) > int(time.time())
                await gate.wait()
                return InternalResponse(
                    content="ok",
                    model="local",
                    daari_meta=DaariMeta(tier="L3", executor="ollama", provider_id="ollama"),
                )

    monkeypatch.setattr("daari.gateway.responses.LEASE_HEARTBEAT_SECONDS", 0.05)
    monkeypatch.setattr("daari.gateway.responses.LEASE_TTL_SECONDS", 2)
    task = asyncio.create_task(
        ResponsesGatewayAdapter._run_background(
            Ctx(),  # type: ignore[arg-type]
            InternalRequest(messages=[Message(role="user", content="hi")], model="daari"),
            "resp_bg",
            2,
            False,
            None,
            [Message(role="user", content="hi")],
            store,
        )
    )
    for _ in range(50):
        row = store.get("resp_bg")
        if row and row.get("status") == "in_progress":
            break
        await asyncio.sleep(0.02)
    mid = store.get("resp_bg")
    assert mid is not None and mid["status"] == "in_progress"
    first_lease = int(mid["_lease_expires_at"] or 0)
    await asyncio.sleep(0.12)
    mid2 = store.get("resp_bg")
    assert mid2 is not None
    assert int(mid2["_lease_expires_at"] or 0) >= first_lease
    gate.set()
    await task
    assert store.get("resp_bg")["status"] == "completed"
    assert seen_statuses == ["in_progress"]


def _responses_store(settings) -> ResponseStore:
    from pathlib import Path

    return ResponseStore(Path(settings.trace.path).expanduser().parent / "responses.sqlite3")


@pytest.mark.asyncio
async def test_get_poll_reclaims_expired_lease(settings, monkeypatch):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    store = _responses_store(settings)
    rid = "resp_dead"
    store.put(
        rid,
        {"id": rid, "object": "response", "status": "queued", "output": []},
        job_owner="dead-pod",
        lease_expires_at=int(time.time()) - 10,
    )
    events: list[str] = []
    monkeypatch.setattr(
        "daari.gateway.responses.log_gateway_event",
        lambda name, fields=None: events.append(name),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        fetched = await client.get(f"/v1/responses/{rid}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["status"] == "failed"
    assert "orphan" in body["error"]["message"].lower()
    assert "responses.job_lease_reclaimed" in events
    assert "_" not in "".join(k for k in body if k.startswith("_"))


@pytest.mark.asyncio
async def test_cancel_orphaned_job_no_duplicate_webhook(settings, monkeypatch):
    settings.alerts.responses_completion_webhook_url = "https://hooks.example/r"
    settings.alerts.responses_completion_webhook_secret = "sec"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    store = _responses_store(settings)
    rid = "resp_orphan_cancel"
    store.put(
        rid,
        {"id": rid, "object": "response", "status": "in_progress", "output": []},
        job_owner="dead-pod",
        lease_expires_at=int(time.time()) - 5,
    )
    seen: list[dict] = []

    def fake_schedule(*, url, secret, body, **kwargs):
        seen.append(body)

    monkeypatch.setattr(
        "daari.gateway.responses.schedule_responses_completion_webhook",
        fake_schedule,
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        cancelled = await client.post(f"/v1/responses/{rid}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "cancelled"
        again = await client.post(f"/v1/responses/{rid}/cancel")
        assert again.json()["status"] == "cancelled"
        polled = await client.get(f"/v1/responses/{rid}")
        assert polled.json()["status"] == "cancelled"
    assert len(seen) == 1
    assert seen[0]["status"] == "cancelled"

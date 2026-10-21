"""GET /v1/daari/events over the postgres request log (#1683)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.gateway import request_log
from daari.gateway.postgres_request_log import PostgresRequestLogStore
from daari.gateway.request_log import configure_request_log
from daari.router.router import AppContext
from daari.server.app import create_app


@pytest.fixture(autouse=True)
def _reset_request_log():
    """create_app() switches the process-wide log backend; restore JSONL after."""
    yield
    configure_request_log(
        path=request_log.DEFAULT_LOG_PATH,
        max_bytes=request_log.DEFAULT_MAX_BYTES,
        backups=request_log.DEFAULT_BACKUPS,
        structured_json_logs=False,
        otlp_logs=False,
        backend="jsonl",
        postgres_url="",
    )


def _dsn() -> str:
    return f"memory:events-http-{uuid.uuid4().hex}"


def _enable_postgres_log(settings, dsn: str) -> None:
    settings.observability.request_log.backend = "postgres"
    settings.observability.postgres_url = dsn


@pytest.mark.asyncio
async def test_events_newest_first_offset_and_cursor(settings):
    dsn = _dsn()
    _enable_postgres_log(settings, dsn)
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    store = PostgresRequestLogStore(dsn)
    store.append("a", {"n": 1, "team_id": "t-a", "key_id": "k-a"})
    store.append("b", {"n": 2, "team_id": "t-a", "key_id": "k-b"})
    store.append("c", {"n": 3, "team_id": "t-b", "key_id": "k-c"})
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get(
            "/v1/daari/events",
            params={"limit": 2, "offset": 0},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page.status_code == 200
        body = page.json()
        assert body["total"] == 3
        assert body["limit"] == 2
        assert body["offset"] == 0
        assert body["has_more"] is True
        assert [row["event"] for row in body["events"]] == ["c", "b"]
        assert body["next_cursor"] == str(body["events"][-1]["id"])

        page2 = await client.get(
            "/v1/daari/events",
            params={"limit": 2, "cursor": body["next_cursor"]},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page2.status_code == 200
        body2 = page2.json()
        assert [row["event"] for row in body2["events"]] == ["a"]
        assert body2["has_more"] is False
        assert body2["next_cursor"] is None

        filtered = await client.get(
            "/v1/daari/events",
            params={"team_id": "t-a", "key_id": "k-b"},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert filtered.status_code == 200
        rows = filtered.json()["events"]
        assert len(rows) == 1
        assert rows[0]["event"] == "b"
        assert rows[0]["payload"]["key_id"] == "k-b"

        defaulted = await client.get(
            "/v1/daari/events",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert defaulted.status_code == 200
        assert defaulted.json()["limit"] == 100

        clamped = await client.get(
            "/v1/daari/events",
            params={"limit": 5000},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert clamped.status_code == 200
        assert clamped.json()["limit"] == 1000
        assert len(clamped.json()["events"]) == 3


@pytest.mark.asyncio
async def test_events_jsonl_backend_is_501(settings):
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    assert settings.observability.request_log.backend == "jsonl"
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/v1/daari/events",
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert resp.status_code == 501


@pytest.mark.asyncio
async def test_events_vk_team_scope(settings, tmp_path):
    dsn = _dsn()
    _enable_postgres_log(settings, dsn)
    settings.server.api_key = "master-sekret"
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    store = VirtualKeyStore(settings.virtual_keys_path)
    team_a = store.create_team("alpha")
    team_b = store.create_team("beta")
    key_a = store.create("alice", team=team_a.name, client_id="alice")
    log = PostgresRequestLogStore(dsn)
    log.append("own", {"team_id": team_a.team_id, "key_id": key_a.key.key_id})
    log.append("other", {"team_id": team_b.team_id, "key_id": "other"})
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/v1/daari/events")
        assert missing.status_code == 401

        forbidden = await client.get(
            "/v1/daari/events",
            params={"team_id": team_b.team_id},
            headers={"Authorization": f"Bearer {key_a.plaintext}"},
        )
        assert forbidden.status_code == 403

        ok = await client.get(
            "/v1/daari/events",
            headers={"Authorization": f"Bearer {key_a.plaintext}"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["team_id"] == team_a.team_id
        assert [row["event"] for row in body["events"]] == ["own"]


def test_query_events_since_until_window():
    """Store path filters by inclusive since / exclusive until (#1824)."""
    dsn = _dsn()
    store = PostgresRequestLogStore(dsn)
    store.append("early", {"n": 1}, ts="2026-10-20T13:00:00+00:00")
    store.append("mid", {"n": 2}, ts="2026-10-20T14:05:00+00:00")
    store.append("late", {"n": 3}, ts="2026-10-20T14:15:00+00:00")
    events, total = store.query_events(
        since="2026-10-20T14:00:00+00:00",
        until="2026-10-20T14:10:00+00:00",
    )
    assert total == 1
    assert [row["event"] for row in events] == ["mid"]


@pytest.mark.asyncio
async def test_events_since_until_and_invalid_400(settings):
    dsn = _dsn()
    _enable_postgres_log(settings, dsn)
    settings.server.api_key = "master-sekret"
    settings.enterprise.sso.enabled = False
    store = PostgresRequestLogStore(dsn)
    store.append("early", {"n": 1}, ts="2026-10-20T13:00:00+00:00")
    store.append("mid", {"n": 2}, ts="2026-10-20T14:05:00+00:00")
    store.append("late", {"n": 3}, ts="2026-10-20T14:15:00+00:00")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        bad = await client.get(
            "/v1/daari/events",
            params={"since": "not-a-date"},
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert bad.status_code == 400

        window = await client.get(
            "/v1/daari/events",
            params={
                "since": "2026-10-20T14:00:00Z",
                "until": "2026-10-20T14:10:00Z",
            },
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert window.status_code == 200
        body = window.json()
        assert [row["event"] for row in body["events"]] == ["mid"]
        assert body["since"].startswith("2026-10-20T14:00:00")
        assert body["until"].startswith("2026-10-20T14:10:00")

        paged = await client.get(
            "/v1/daari/events",
            params={
                "since": "2026-10-20T13:00:00Z",
                "until": "2026-10-20T15:00:00Z",
                "limit": 1,
            },
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert paged.status_code == 200
        first = paged.json()
        assert first["events"][0]["event"] == "late"
        assert first["has_more"] is True
        page2 = await client.get(
            "/v1/daari/events",
            params={
                "since": "2026-10-20T13:00:00Z",
                "until": "2026-10-20T15:00:00Z",
                "cursor": first["next_cursor"],
            },
            headers={"Authorization": "Bearer master-sekret"},
        )
        assert page2.status_code == 200
        assert [row["event"] for row in page2.json()["events"]] == ["mid", "early"]

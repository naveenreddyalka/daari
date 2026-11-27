"""Per-key/team zero_retention: no tenant prompt bytes in on-box stores (#2347)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore, zero_retention_enforced
from daari.gateway.internal import (
    DaariMeta,
    InternalRequest,
    InternalResponse,
    Message,
    RequestMeta,
)
from daari.router.router import AppContext, _skip_prompt_cache_put
from daari.server.app import create_app
from daari.server.auth import _claims_from_virtual_key
from daari.setup.doctor import _check_zero_retention


def test_key_or_team_true_enforces_and_key_cannot_loosen(tmp_path):
    store = VirtualKeyStore(tmp_path / "vk.sqlite3")
    team = store.create_team("eng", metadata={"zero_retention": True})
    created = store.create("loose", team="eng", metadata={"zero_retention": False})
    key = next(row for row in store.list() if row.key_id == created.key.key_id)
    loaded_team = store.get_team(team.team_id)
    assert key.zero_retention is False
    assert loaded_team is not None and loaded_team.zero_retention is True
    assert zero_retention_enforced(key, loaded_team) is True
    claims = _claims_from_virtual_key(key, store)
    assert claims.zero_retention is True

    open_team = store.create_team("ops", metadata={"zero_retention": False})
    tight = store.create("tight", team="ops", metadata={"zero_retention": True})
    tight_key = next(row for row in store.list() if row.key_id == tight.key.key_id)
    assert zero_retention_enforced(tight_key, store.get_team(open_team.team_id)) is True

    plain = store.create("plain", metadata={})
    plain_key = next(row for row in store.list() if row.key_id == plain.key.key_id)
    assert zero_retention_enforced(plain_key, None) is False


def test_doctor_counts_zero_retention_keys_and_teams(settings, tmp_path):
    settings.server.virtual_keys.enabled = True
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("eng", metadata={"zero_retention": True})
    store.create("alice", metadata={"zero_retention": True})
    store.create("bob", metadata={})
    result = _check_zero_retention(settings)
    assert result.name == "zero_retention"
    assert result.ok is True
    assert "keys=1" in result.detail
    assert "teams=1" in result.detail


def _request(zero: bool) -> InternalRequest:
    return InternalRequest(
        messages=[Message(role="user", content="tenant prompt")],
        model="llama3.2:3b",
        meta=RequestMeta(zero_retention=zero),
    )


def _response() -> InternalResponse:
    return InternalResponse(
        content="answer",
        model="llama3.2:3b",
        daari_meta=DaariMeta(tier="L3", executor="ollama", latency_ms=1),
    )


@pytest.mark.asyncio
async def test_zero_retention_skips_cache_puts():
    puts: list[str] = []

    class Cache:
        def put(self, request, response):
            puts.append("l0")

    class Org:
        async def put_l0(self, request, response):
            puts.append("org-l0")

        async def put_l1(self, request, response):
            puts.append("org-l1")

    class Semantic:
        async def put(self, request, response):
            puts.append("semantic")

        async def put_agent_prefix(self, request, response):
            puts.append("prefix")

    class Host:
        cache = Cache()
        org_cache_client = Org()
        semantic_cache = Semantic()

    from daari.router.router import Router

    await Router._write_prompt_caches(Host(), _request(True), _response())
    assert puts == []
    assert _skip_prompt_cache_put(_request(True)) is True
    await Router._write_prompt_caches(Host(), _request(False), _response())
    assert puts == ["l0", "org-l0", "semantic", "org-l1"]


@pytest.mark.asyncio
async def test_responses_store_skipped_and_chain_is_not_found(settings, tmp_path):
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.trace.path = str(tmp_path / "trace.jsonl")
    store = VirtualKeyStore(settings.virtual_keys_path)
    created = store.create("zdr", client_id="zdr", metadata={"zero_retention": True})
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async def fake_route(request: InternalRequest) -> InternalResponse:
        assert request.meta.zero_retention is True
        return _response()

    app.state.ctx.router.route = fake_route
    headers = {"Authorization": f"Bearer {created.plaintext}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "secret", "store": True},
            headers=headers,
        )
        assert first.status_code == 200
        rid = first.json()["id"]
        fetched = await client.get(f"/v1/responses/{rid}", headers=headers)
        assert fetched.status_code == 404
        chained = await client.post(
            "/v1/responses",
            json={"model": "daari", "input": "next", "previous_response_id": rid},
            headers=headers,
        )
        assert chained.status_code == 400
        assert "previous_response_id not found" in chained.json()["detail"]

"""Decisions L0 cache_scope tenancy isolation (#1554)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.virtual_keys import VirtualKeyStore
from daari.router.router import AppContext
from daari.server.app import create_app
from tests.unit.test_decisions import _BODY, _SYSTEMONE_OK, _patch_local


def _app(settings):
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    return app


@pytest.mark.asyncio
async def test_decisions_cache_scope_key_isolates_l0(settings, monkeypatch, tmp_path):
    """Two cache_scope=key VKs must not L0-hit each other's identical bodies."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = True
    settings.cache.l0.path = str(tmp_path / "l0")
    settings.decisions.cache_enabled = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    left = store.create("left", client_id="left", cache_scope="key")
    right = store.create("right", client_id="right", cache_scope="key")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {left.plaintext}"},
        )
        cross = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {right.plaintext}"},
        )
        again = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {left.plaintext}"},
        )

    assert first.status_code == 200
    assert first.json()["daari_meta"]["tier"] == "decisions"
    assert first.json()["daari_meta"]["cache_hit"] is False

    assert cross.status_code == 200
    assert cross.json()["daari_meta"]["tier"] == "decisions"
    assert cross.json()["daari_meta"]["cache_hit"] is False

    assert again.status_code == 200
    assert again.json()["daari_meta"]["tier"] == "L0"
    assert again.json()["daari_meta"]["cache_hit"] is True
    assert again.json()["answers"] == first.json()["answers"]
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_decisions_cache_scope_team_isolates_across_teams(
    settings, monkeypatch, tmp_path
):
    """Same-team hit / cross-team miss for cache_scope=team (#1554)."""
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json=_SYSTEMONE_OK)

    _patch_local(monkeypatch, handler)
    settings.ollama.base_url = "http://ollama.local:11434"
    settings.server.api_key = "master"
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.cache.l0.enabled = True
    settings.cache.l0.path = str(tmp_path / "l0")
    settings.decisions.cache_enabled = True
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("eng", cache_scope="team")
    store.create_team("ops", cache_scope="team")
    a = store.create("a", client_id="a", team="eng", cache_scope="team")
    b = store.create("b", client_id="b", team="eng", cache_scope="team")
    c = store.create("c", client_id="c", team="ops", cache_scope="team")
    app = _app(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {a.plaintext}"},
        )
        teammate = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {b.plaintext}"},
        )
        other = await client.post(
            "/v1/decisions",
            json=_BODY,
            headers={"Authorization": f"Bearer {c.plaintext}"},
        )

    assert first.status_code == 200
    assert first.json()["daari_meta"]["cache_hit"] is False
    assert teammate.status_code == 200
    assert teammate.json()["daari_meta"]["tier"] == "L0"
    assert teammate.json()["daari_meta"]["cache_hit"] is True
    assert other.status_code == 200
    assert other.json()["daari_meta"]["tier"] == "decisions"
    assert other.json()["daari_meta"]["cache_hit"] is False
    assert calls["n"] == 2

"""Per-team / per-key frontier credential binding (team BYOK) (#2216)."""

from __future__ import annotations

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from daari.auth.frontier_binding import (
    FrontierBindingError,
    binding_from_meta,
    resolve_bound_key,
    write_binding_to_meta,
)
from daari.auth.virtual_keys import VirtualKeyStore
from daari.enterprise.postgres_audit import audit_log_from_settings
from daari.gateway.admin_read import redact_key, redact_team
from daari.gateway.internal import DaariMeta, InternalRequest, InternalResponse, Message
from daari.router.frontier import FrontierExecutor
from daari.router.frontier_pool import FrontierPool, ProviderSlot
from daari.router.router import AppContext
from daari.security.secret_refs import REDACTED, SecretRefError
from daari.server.app import create_app
from daari.setup.doctor import _check_team_frontier_bindings, run_doctor


def _request(**meta_kwargs) -> InternalRequest:
    from daari.gateway.internal import RequestMeta

    return InternalRequest(
        messages=[Message(role="user", content="escalate me")],
        model="daari",
        meta=RequestMeta(**meta_kwargs),
    )


def _ok(provider: str = "primary") -> InternalResponse:
    return InternalResponse(
        content=f"answer from {provider}",
        model="gpt-4o-mini",
        daari_meta=DaariMeta(
            tier="L6",
            executor="frontier",
            provider_id=provider,
            latency_ms=10,
            model="gpt-4o-mini",
        ),
    )


def test_binding_meta_roundtrip_and_redact():
    meta = write_binding_to_meta(
        {},
        frontier_api_key="secret://env-file/tmp/keys.env#TEAM_KEY",
        frontier_pool="openai-byok",
    )
    assert binding_from_meta(meta) == (
        "secret://env-file/tmp/keys.env#TEAM_KEY",
        "openai-byok",
    )
    cleared = write_binding_to_meta(meta, frontier_api_key=None, frontier_pool=None)
    assert binding_from_meta(cleared) == (None, None)


def test_resolve_bound_key_plain_and_fail_closed(monkeypatch):
    assert resolve_bound_key("sk-team-plain") == "sk-team-plain"

    def boom(ref):
        raise SecretRefError(f"cannot resolve {ref!r}")

    monkeypatch.setattr("daari.auth.frontier_binding.resolve_secret_ref", boom)
    with pytest.raises(FrontierBindingError, match="unresolvable"):
        resolve_bound_key("secret://env-file/missing.env#K")

    with pytest.raises(FrontierBindingError, match="empty"):
        resolve_bound_key("   ")


def test_store_team_and_key_frontier_binding(tmp_path):
    store = VirtualKeyStore(str(tmp_path / "vk.sqlite3"))
    team = store.create_team(
        "eng",
        frontier_api_key="secret://env-file/keys.env#ENG",
        frontier_pool="openai-byok",
    )
    assert team.frontier_api_key == "secret://env-file/keys.env#ENG"
    assert team.frontier_pool == "openai-byok"
    loaded = store.get_team(team.team_id)
    assert loaded is not None
    assert loaded.frontier_api_key == "secret://env-file/keys.env#ENG"
    assert loaded.frontier_pool == "openai-byok"

    created = store.create(
        "alice",
        team="eng",
        frontier_api_key="sk-key-override",
    )
    found = store.resolve(created.plaintext)
    assert found is not None
    assert found.frontier_api_key == "sk-key-override"

    assert store.update_team_frontier_binding(
        team.team_id, frontier_api_key="sk-team-2", frontier_pool=None
    )
    assert store.get_team(team.team_id).frontier_api_key == "sk-team-2"
    assert store.get_team(team.team_id).frontier_pool is None

    assert store.update_frontier_binding(created.key.key_id, frontier_api_key=None)
    assert store.resolve(created.plaintext).frontier_api_key is None

    redacted = redact_team(store.get_team(team.team_id))
    assert redacted["frontier_api_key"] == REDACTED
    assert "sk-team-2" not in str(redacted)
    assert redacted.get("frontier_pool") is None

    key_row = redact_key(store.resolve(created.plaintext))
    assert key_row["frontier_api_key"] is None


@pytest.mark.asyncio
async def test_pool_uses_bound_key_unbound_falls_back():
    captured: list[str | None] = []
    executor = FrontierExecutor(
        base_url="http://primary", default_model="a", api_key="sk-global", provider="primary"
    )

    async def ok(request, *, escalated_from, local_confidence):
        captured.append(executor.api_key)
        return _ok()

    executor.execute = ok  # type: ignore[method-assign]
    pool = FrontierPool(
        slots=[ProviderSlot(id="primary", executor=executor, keys=["sk-global"])]
    )

    unbound = await pool.execute(_request(), escalated_from="L3", local_confidence=0.2)
    assert unbound.content.startswith("answer")
    assert captured[-1] == "sk-global"

    bound = await pool.execute(
        _request(frontier_api_key="sk-team-byok"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert bound.content.startswith("answer")
    assert captured[-1] == "sk-team-byok"


@pytest.mark.asyncio
async def test_pool_bound_key_auth_header_and_fail_closed(monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    executor = FrontierExecutor(
        base_url="http://frontier.test",
        default_model="gpt-4o-mini",
        api_key="sk-global",
        provider="openai",
        transport=httpx.MockTransport(handler),
    )
    pool = FrontierPool.from_single(executor)

    await pool.execute(
        _request(frontier_api_key="sk-team-secret"),
        escalated_from="L3",
        local_confidence=0.1,
    )
    assert seen and seen[-1] == "Bearer sk-team-secret"

    def boom(_ref):
        raise SecretRefError("gone")

    monkeypatch.setattr("daari.auth.frontier_binding.resolve_secret_ref", boom)
    with pytest.raises(FrontierBindingError, match="unresolvable"):
        await pool.execute(
            _request(frontier_api_key="secret://env-file/x.env#K"),
            escalated_from="L3",
            local_confidence=0.1,
        )


@pytest.mark.asyncio
async def test_pool_named_frontier_pool_slot():
    captured: list[str] = []
    primary = FrontierExecutor(
        base_url="http://p", default_model="a", api_key="sk-p", provider="primary"
    )
    byok = FrontierExecutor(
        base_url="http://b", default_model="b", api_key="sk-byok", provider="openai-byok"
    )

    async def fail(**kwargs):
        raise RuntimeError("should not call primary")

    async def ok(request, *, escalated_from, local_confidence):
        captured.append(byok.api_key or "")
        return _ok("openai-byok")

    primary.execute = fail  # type: ignore[method-assign]
    byok.execute = ok  # type: ignore[method-assign]
    pool = FrontierPool(
        slots=[
            ProviderSlot(id="primary", executor=primary, keys=["sk-p"]),
            ProviderSlot(id="openai-byok", executor=byok, keys=["sk-byok"]),
        ]
    )
    result = await pool.execute(
        _request(frontier_pool="openai-byok"),
        escalated_from="L3",
        local_confidence=0.2,
    )
    assert result.daari_meta.provider_id == "openai-byok"
    assert captured == ["sk-byok"]

    with pytest.raises(FrontierBindingError, match="frontier_pool"):
        await pool.execute(
            _request(frontier_pool="missing-slot"),
            escalated_from="L3",
            local_confidence=0.2,
        )


def _app_with_store(settings, tmp_path, *, master: str = "master-sekret"):
    settings.server.api_key = master
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    settings.enterprise.sso.enabled = False
    settings.enterprise.audit_path = str(tmp_path / "audit.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    team = store.create_team("eng")
    created = store.create("alice", team="eng")
    vk = store.create("viewer")
    app = create_app(settings)
    app.state.ctx = AppContext.from_settings(settings)
    app.state.virtual_key_store = store
    app.state.ctx.virtual_key_store = store
    return app, store, created, team, vk


@pytest.mark.asyncio
async def test_admin_patch_team_frontier_binding_redacted(settings, tmp_path):
    app, store, _created, team, vk = _app_with_store(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.patch(
            f"/v1/daari/teams/{team.team_id}",
            headers={"Authorization": f"Bearer {vk.plaintext}"},
            json={"frontier_api_key": "sk-secret"},
        )
        assert denied.status_code == 403

        ok = await client.patch(
            f"/v1/daari/teams/{team.team_id}",
            headers={
                "Authorization": "Bearer master-sekret",
                "x-daari-actor": "ops-bob",
            },
            json={
                "frontier_api_key": "secret://env-file/keys.env#ENG",
                "frontier_pool": "openai-byok",
            },
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["frontier_api_key"] == REDACTED
        assert body["frontier_pool"] == "openai-byok"
        assert "secret://" not in str(body.get("frontier_api_key"))
        loaded = store.get_team(team.team_id)
        assert loaded.frontier_api_key == "secret://env-file/keys.env#ENG"
        assert loaded.frontier_pool == "openai-byok"

        cleared = await client.patch(
            f"/v1/daari/teams/{team.team_id}",
            headers={"Authorization": "Bearer master-sekret"},
            json={"frontier_api_key": None, "frontier_pool": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["frontier_api_key"] is None
        assert cleared.json()["frontier_pool"] is None

    rows = audit_log_from_settings(settings).list(action="admin.teams.patch_frontier")
    assert len(rows) >= 1
    assert any(row.get("actor") == "ops-bob" for row in rows)
    for row in rows:
        detail = row.get("detail") or {}
        assert "sk-" not in str(detail)
        assert "secret://" not in str(detail)


@pytest.mark.asyncio
async def test_admin_patch_key_frontier_binding_redacted(settings, tmp_path):
    app, store, created, _team, _vk = _app_with_store(settings, tmp_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        ok = await client.patch(
            f"/v1/daari/keys/{created.key.key_id}",
            headers={"Authorization": "Bearer master-sekret"},
            json={"frontier_api_key": "sk-key-byok"},
        )
        assert ok.status_code == 200
        assert ok.json()["frontier_api_key"] == REDACTED
        assert store.resolve(created.plaintext).frontier_api_key == "sk-key-byok"


def test_doctor_tips_unresolvable_team_binding(settings, tmp_path, monkeypatch):
    settings.server.virtual_keys.path = str(tmp_path / "vk.sqlite3")
    store = VirtualKeyStore(settings.virtual_keys_path)
    store.create_team("eng", frontier_api_key="secret://env-file/missing.env#K")

    def boom(ref, **kwargs):
        raise SecretRefError("nope")

    monkeypatch.setattr("daari.auth.frontier_binding.resolve_secret_ref", boom)
    monkeypatch.setattr(
        "daari.auth.postgres_virtual_keys.virtual_key_store_from_settings",
        lambda _s: store,
    )
    tip = _check_team_frontier_bindings(settings)
    assert tip is not None
    assert tip.ok is False or tip.optional is True
    assert "eng" in tip.detail
    assert "frontier" in tip.detail.lower()

    results = run_doctor(settings)
    names = {r.name for r in results}
    assert "team_frontier_bindings" in names
